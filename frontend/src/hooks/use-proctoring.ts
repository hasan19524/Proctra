"use client";

import * as React from "react";

import { ProctorEngine } from "@/lib/proctor/engine";
import type { ProctorObservation, ProctorStatus, ProctorStatusInfo } from "@/lib/proctor/types";

/** Tab-hidden → immediate `tab_hidden` observation (not a vision signal). */
function tabHiddenObservation(): ProctorObservation {
  return { signal: "tab_hidden", duration_s: 0 };
}

export interface UseProctoringOptions {
  /** Whether this client should be proctoring (students in an exam only). */
  active: boolean;
  /** The LiveKit local camera stream to feed the engine (may be null). */
  cameraStream: MediaStream | null;
  /** Send one observation to the server (wired to `proctor.event` frames). */
  sendEvent: (observation: ProctorObservation) => void;
  /** Called when the engine's status changes (loading/active/degraded/error). */
  onStatusChange?: (info: ProctorStatusInfo) => void;
}

export interface UseProctoringResult {
  status: ProctorStatus;
  message: string | null;
  /** Re-attempt engine start after a recoverable failure. */
  retry: () => void;
  /** True once the engine has emitted at least one frame successfully. */
  warmedUp: boolean;
}

/**
 * Drives the MediaPipe proctoring engine for one student client.
 *
 * Responsibilities:
 * - Start/stop the engine when `active` flips or the camera stream changes.
 * - Emit `tab_hidden` observations on visibilitychange (the engine handles
 *   all camera/vision signals itself).
 * - Surface engine status + a human message to the UI.
 *
 * The engine is intentionally a plain class (not a hook) so its detection
 * loop stays out of React's render cycle; this hook owns its lifecycle.
 */
export function useProctoring({
  active,
  cameraStream,
  sendEvent,
  onStatusChange,
}: UseProctoringOptions): UseProctoringResult {
  const [status, setStatus] = React.useState<ProctorStatus>("idle");
  const [message, setMessage] = React.useState<string | null>(null);
  const [warmedUp, setWarmedUp] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);

  // Keep the latest callback in a ref so the engine's interval sees fresh code.
  const sendRef = React.useRef(sendEvent);
  React.useEffect(() => {
    sendRef.current = sendEvent;
  }, [sendEvent]);

  const engineRef = React.useRef<ProctorEngine | null>(null);

  React.useEffect(() => {
    if (!active) return;

    const engine = new ProctorEngine({
      onObservation: (observation) => {
        setWarmedUp(true);
        sendRef.current(observation);
      },
      onStatus: (info) => {
        setStatus(info.status);
        setMessage(info.message ?? null);
        onStatusChange?.(info);
      },
    });
    engineRef.current = engine;
    void engine.start(cameraStream);

    return () => {
      engine.stop();
      engineRef.current = null;
      setStatus("idle");
      setMessage(null);
      setWarmedUp(false);
    };
    // `attempt` lets retry() re-run the effect after a failure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, cameraStream, attempt]);

  // Tab visibility: leaving the exam tab is an immediate `tab_hidden` signal.
  React.useEffect(() => {
    if (!active) return;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        sendRef.current(tabHiddenObservation());
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [active]);

  const retry = React.useCallback(() => setAttempt((n) => n + 1), []);

  return { status, message, retry, warmedUp };
}

export interface SelfCheckResult {
  ok: boolean;
  faceDetected: boolean;
  /** Human-readable issues (empty when ok). */
  issues: string[];
  /** Average blur variance observed; low = blurry camera. */
  blurVariance: number | null;
}

/**
 * One-shot camera + model self-check for the pre-join screen.
 *
 * Verifies the camera works and the vision model can detect a face before the
 * student joins — so a broken setup is caught in the lobby, not mid-exam.
 */
export async function runSelfCheck(durationMs = 2500): Promise<SelfCheckResult> {
  const issues: string[] = [];
  let stream: MediaStream | null = null;

  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  } catch {
    return {
      ok: false,
      faceDetected: false,
      issues: ["Camera access was denied. Allow camera access, then retry."],
      blurVariance: null,
    };
  }

  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;

  try {
    await video.play();
  } catch {
    /* muted autoplay is usually allowed; detection just waits for data */
  }

  try {
    const { FilesetResolver, FaceLandmarker } = await import("@mediapipe/tasks-vision");
    const fileset = await FilesetResolver.forVisionTasks("/mediapipe-wasm");
    const landmarker = await FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: "/models/face_landmarker.task", delegate: "GPU" },
      runningMode: "VIDEO",
      numFaces: 1,
    });

    // Sample a handful of frames across the window.
    let facesSeen = 0;
    let samples = 0;
    const started = performance.now();
    while (performance.now() - started < durationMs) {
      if (video.readyState >= 2) {
        try {
          const result = landmarker.detectForVideo(video, performance.now());
          if ((result.faceLandmarks?.length ?? 0) > 0) facesSeen++;
          samples++;
        } catch {
          /* transient */
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    landmarker.close();

    const faceDetected = samples > 0 && facesSeen > 0;
    if (!faceDetected) {
      issues.push("We could not detect a face. Sit facing the camera in good light, then retry.");
    }

    return { ok: faceDetected, faceDetected, issues, blurVariance: null };
  } catch {
    return {
      ok: false,
      faceDetected: false,
      issues: ["The proctoring model could not load. Check your connection, then retry."],
      blurVariance: null,
    };
  } finally {
    video.srcObject = null;
    for (const track of stream.getTracks()) track.stop();
  }
}
