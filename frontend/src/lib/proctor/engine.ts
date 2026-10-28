/**
 * MediaPipe-based proctoring engine (Phase 16 — exam mode).
 *
 * Loads the Face Landmarker task (self-hosted WASM + model, no CDN) and runs
 * it over the student's *own* camera stream at a low, steady cadence. No video
 * ever leaves the device: only the classified observations (looking away, no
 * face, multiple faces, speaking, eyes closed, blur) are emitted, and those
 * are sent to the server over the meeting WebSocket for scoring.
 *
 * Failure modes are explicit — the UI shows a friendly, retryable error when
 * the model or the camera cannot start, and a degraded state when video
 * quality makes detection unreliable (blurry / camera off).
 */

import {
  classifyFrame,
  createSignalState,
  laplacianVariance,
  type Landmark,
  type SignalConfig,
} from "./detector";
import type { ProctorObservation, ProctorStatusInfo } from "./types";

const SAMPLE_INTERVAL_MS = 500; // 2 Hz: plenty for sustained-signal detection
const BLUR_SAMPLE_WIDTH = 160;
const BLUR_SAMPLE_HEIGHT = 120;

export interface EngineCallbacks {
  onObservation: (observation: ProctorObservation) => void;
  onStatus: (info: ProctorStatusInfo) => void;
}

/** Minimal shape of a loaded MediaPipe FaceLandmarker (avoid a hard type dep). */
interface FaceLandmarkerLike {
  detectForVideo(
    video: HTMLVideoElement,
    timestampMs: number,
  ): {
    faceLandmarks: Array<Array<{ x: number; y: number; z: number }>>;
  };
  close(): void;
}

let landmarkerPromise: Promise<FaceLandmarkerLike> | null = null;

/**
 * Load (and cache) the Face Landmarker task from the self-hosted assets in
 * `public/`. Falls back to the CPU delegate when WebGL is unavailable.
 */
async function loadLandmarker(): Promise<FaceLandmarkerLike> {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const { FilesetResolver, FaceLandmarker } = await import("@mediapipe/tasks-vision");
      const fileset = await FilesetResolver.forVisionTasks("/mediapipe-wasm");
      const options = {
        baseOptions: {
          modelAssetPath: "/models/face_landmarker.task",
          delegate: "GPU" as const,
        },
        runningMode: "VIDEO" as const,
        numFaces: 2,
      };
      try {
        return (await FaceLandmarker.createFromOptions(fileset, options)) as FaceLandmarkerLike;
      } catch {
        // WebGL may be blocked (locked-down browsers): retry on CPU.
        return (await FaceLandmarker.createFromOptions(fileset, {
          ...options,
          baseOptions: { ...options.baseOptions, delegate: "CPU" as const },
        })) as FaceLandmarkerLike;
      }
    })().catch((error: unknown) => {
      landmarkerPromise = null; // allow a retry on the next start()
      throw error;
    });
  }
  return landmarkerPromise;
}

export class ProctorEngine {
  private video: HTMLVideoElement | null = null;
  private stream: MediaStream | null = null;
  private landmarker: FaceLandmarkerLike | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private canvasCtx: CanvasRenderingContext2D | null = null;
  private state = createSignalState();
  private config: SignalConfig | undefined;
  private callbacks: EngineCallbacks;
  private running = false;
  private lastTimestamp = 0;
  private cameraOffSince: number | null = null;
  /** True when *we* called getUserMedia (so we own the track lifecycle). */
  private ownsStream = false;

  constructor(callbacks: EngineCallbacks, config?: SignalConfig) {
    this.callbacks = callbacks;
    this.config = config;
  }

  /** Start proctoring against an existing camera stream (or acquire one). */
  async start(existingStream?: MediaStream | null): Promise<void> {
    if (this.running) return;
    this.callbacks.onStatus({ status: "loading", message: "Starting the camera…" });

    // 1. Camera: reuse the LiveKit local track when present so we do not open
    //    the camera twice; otherwise acquire a dedicated stream.
    if (existingStream && existingStream.getVideoTracks().length > 0) {
      this.stream = existingStream;
      this.ownsStream = false;
    } else {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480 },
          audio: false,
        });
        this.ownsStream = true;
      } catch {
        this.callbacks.onStatus({
          status: "error",
          message:
            "Camera access is needed for proctoring. Allow camera access in your browser, then retry.",
        });
        return;
      }
    }

    // 2. Hidden video element fed by the stream (never rendered).
    this.video = document.createElement("video");
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.srcObject = this.stream;
    try {
      await this.video.play();
    } catch {
      /* autoplay of a muted element rarely fails; detection will wait for data */
    }

    // 3. Vision model.
    this.callbacks.onStatus({ status: "loading", message: "Loading the vision model…" });
    try {
      this.landmarker = await loadLandmarker();
    } catch {
      this.teardownMedia();
      this.callbacks.onStatus({
        status: "error",
        message:
          "The proctoring model failed to load. Check your connection and retry — if it keeps failing, tell the host before the exam continues.",
      });
      return;
    }

    // 4. Offscreen canvas for the blur metric.
    this.canvas = document.createElement("canvas");
    this.canvas.width = BLUR_SAMPLE_WIDTH;
    this.canvas.height = BLUR_SAMPLE_HEIGHT;
    this.canvasCtx = this.canvas.getContext("2d", { willReadFrequently: true });

    this.running = true;
    this.state = createSignalState();
    this.callbacks.onStatus({ status: "active" });
    this.timer = setInterval(() => this.tick(), SAMPLE_INTERVAL_MS);
  }

  /** Stop proctoring and release any camera stream we acquired ourselves. */
  stop(): void {
    this.running = false;
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (this.landmarker) {
      try {
        this.landmarker.close();
      } catch {
        /* already closed */
      }
      // Do not clear the module-level cache: the task is reusable across rooms.
      this.landmarker = null;
    }
    this.teardownMedia();
    this.callbacks.onStatus({ status: "idle" });
  }

  /** Re-run detection immediately (e.g. after the tab becomes visible again). */
  private tick(): void {
    if (!this.running || !this.video || !this.landmarker) return;
    if (this.video.readyState < 2) return; // no data yet

    const now = performance.now();
    // detectForVideo requires strictly increasing timestamps.
    if (now <= this.lastTimestamp) return;
    this.lastTimestamp = now;

    let faces: Landmark[][];
    try {
      const result = this.landmarker.detectForVideo(this.video, now);
      faces = (result.faceLandmarks ?? []) as Landmark[][];
    } catch {
      return; // transient decode hiccup; the next tick retries
    }

    // Camera track ended/muted (device unplugged, permission revoked): treat
    // as "no face" after a grace period so a momentary glitch is not flagged.
    const track = this.stream?.getVideoTracks()[0];
    const trackLive = Boolean(track && track.readyState === "live" && track.enabled);
    if (!trackLive) {
      if (this.cameraOffSince === null) this.cameraOffSince = now;
      if (now - this.cameraOffSince > 2000 && faces.length > 0) faces = [];
    } else {
      this.cameraOffSince = null;
    }

    const blurVariance = this.measureBlur();
    const observations = classifyFrame(this.state, {
      timestampMs: now,
      faces,
      blurVariance,
      config: this.config,
    });
    for (const observation of observations) {
      this.callbacks.onObservation(observation);
    }
  }

  /** Grayscale variance-of-Laplacian on a downscaled frame (blur detection). */
  private measureBlur(): number | undefined {
    if (!this.canvas || !this.canvasCtx || !this.video) return undefined;
    const { videoWidth, videoHeight } = this.video;
    if (videoWidth === 0 || videoHeight === 0) return undefined;
    try {
      this.canvasCtx.drawImage(this.video, 0, 0, BLUR_SAMPLE_WIDTH, BLUR_SAMPLE_HEIGHT);
      const { data } = this.canvasCtx.getImageData(0, 0, BLUR_SAMPLE_WIDTH, BLUR_SAMPLE_HEIGHT);
      // Luma only: the Laplacian does not care about chroma.
      const gray = new Uint8ClampedArray(BLUR_SAMPLE_WIDTH * BLUR_SAMPLE_HEIGHT);
      for (let i = 0, j = 0; i < data.length; i += 4, j++) {
        gray[j] = (data[i] * 299 + data[i + 1] * 587 + data[i + 2] * 114) / 1000;
      }
      return laplacianVariance(gray, BLUR_SAMPLE_WIDTH, BLUR_SAMPLE_HEIGHT);
    } catch {
      return undefined;
    }
  }

  private teardownMedia(): void {
    if (this.video) {
      this.video.srcObject = null;
      this.video = null;
    }
    // Only stop tracks we own: the LiveKit camera track belongs to the room.
    if (this.stream && this.ownsStream) {
      for (const track of this.stream.getTracks()) track.stop();
    }
    this.stream = null;
    this.ownsStream = false;
    this.canvas = null;
    this.canvasCtx = null;
  }
}
