/**
 * Pure proctoring classification (Phase 16 — exam mode).
 *
 * Every function here is deterministic and framework-free so the thresholds
 * can be unit-tested with synthetic landmarks — no MediaPipe, no DOM. The
 * engine (engine.ts) feeds it real detections; this file decides what a face
 * is *doing*.
 */

import type { ProctorObservation, ProctorSignal } from "./types";

/** One normalized landmark (MediaPipe face-mesh point). */
export interface Landmark {
  x: number;
  y: number;
  z?: number;
}

// MediaPipe 478-point face-mesh indices used for pose/blink/mouth geometry.
const NOSE_TIP = 1;
const LEFT_EYE_OUTER = 33;
const LEFT_EYE_INNER = 133;
const LEFT_EYE_TOP = 159;
const LEFT_EYE_BOTTOM = 145;
const RIGHT_EYE_OUTER = 362;
const RIGHT_EYE_INNER = 263;
const RIGHT_EYE_TOP = 386;
const RIGHT_EYE_BOTTOM = 374;
const MOUTH_LEFT = 61;
const MOUTH_RIGHT = 291;
const MOUTH_TOP = 13;
const MOUTH_BOTTOM = 14;

/**
 * Thresholds tuned for headroom against false positives: every signal needs
 * the condition to hold continuously for `minActiveMs` before it fires, and
 * the same signal cannot re-fire within `cooldownMs`.
 */
export interface SignalConfig {
  lookingAway: { minActiveMs: number; cooldownMs: number; yawThreshold: number };
  noFace: { minActiveMs: number; cooldownMs: number };
  multipleFaces: { minActiveMs: number; cooldownMs: number };
  speaking: { minActiveMs: number; cooldownMs: number; opennessThreshold: number };
  eyesClosed: { minActiveMs: number; cooldownMs: number; earThreshold: number };
  videoBlur: { minActiveMs: number; cooldownMs: number; varianceThreshold: number };
  /** Faces smaller than this (fraction of frame width) are too small to judge. */
  minFaceWidth: number;
}

export const DEFAULT_CONFIG: SignalConfig = {
  lookingAway: { minActiveMs: 2500, cooldownMs: 10_000, yawThreshold: 0.18 },
  noFace: { minActiveMs: 3000, cooldownMs: 10_000 },
  multipleFaces: { minActiveMs: 2000, cooldownMs: 10_000 },
  speaking: { minActiveMs: 2000, cooldownMs: 10_000, opennessThreshold: 0.4 },
  eyesClosed: { minActiveMs: 2000, cooldownMs: 10_000, earThreshold: 0.19 },
  videoBlur: { minActiveMs: 3000, cooldownMs: 30_000, varianceThreshold: 60 },
  minFaceWidth: 0.08,
};

/** Per-signal episode state: when the condition started and when it last fired. */
export interface SignalState {
  activeSince: Partial<Record<ProctorSignal, number>>;
  lastFired: Partial<Record<ProctorSignal, number>>;
}

export function createSignalState(): SignalState {
  return { activeSince: {}, lastFired: {} };
}

function dist(a: Landmark, b: Landmark): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** Face bounding box from landmarks (normalized 0..1 coordinates). */
export function faceBox(landmarks: Landmark[]): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  width: number;
} {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const point of landmarks) {
    if (point.x < minX) minX = point.x;
    if (point.x > maxX) maxX = point.x;
    if (point.y < minY) minY = point.y;
    if (point.y > maxY) maxY = point.y;
  }
  return { minX, maxX, minY, maxY, width: maxX - minX };
}

/**
 * Head yaw estimate in roughly -0.5..0.5: horizontal offset of the nose tip
 * from the eye-line midpoint, normalized by interpupillary distance. When the
 * head turns, the nose slides toward one eye; a frontal face keeps it centered.
 */
export function estimateYaw(landmarks: Landmark[]): number {
  const left = landmarks[LEFT_EYE_OUTER];
  const right = landmarks[RIGHT_EYE_OUTER];
  const nose = landmarks[NOSE_TIP];
  if (!left || !right || !nose) return 0;
  const midX = (left.x + right.x) / 2;
  const ipd = Math.max(dist(left, right), 1e-6);
  return (nose.x - midX) / ipd;
}

/**
 * Head pitch estimate: nose tip below the eye line (positive = looking down,
 * e.g. at a phone or notes on the desk), normalized by eye-to-chin distance.
 */
export function estimatePitch(landmarks: Landmark[]): number {
  const left = landmarks[LEFT_EYE_OUTER];
  const right = landmarks[RIGHT_EYE_OUTER];
  const nose = landmarks[NOSE_TIP];
  const chin = landmarks[MOUTH_BOTTOM];
  if (!left || !right || !nose || !chin) return 0;
  const eyeY = (left.y + right.y) / 2;
  const span = Math.max(chin.y - eyeY, 1e-6);
  return (nose.y - eyeY) / span;
}

/**
 * Eye aspect ratio: vertical eye opening over horizontal eye width, averaged
 * across both eyes. A wide-open eye is ~0.25-0.30; a closed eye drops under
 * ~0.19 (the blink/`eyes_closed` threshold).
 */
export function eyeAspectRatio(landmarks: Landmark[]): number {
  const pairs: Array<
    [Landmark | undefined, Landmark | undefined, Landmark | undefined, Landmark | undefined]
  > = [
    [
      landmarks[LEFT_EYE_TOP],
      landmarks[LEFT_EYE_BOTTOM],
      landmarks[LEFT_EYE_OUTER],
      landmarks[LEFT_EYE_INNER],
    ],
    [
      landmarks[RIGHT_EYE_TOP],
      landmarks[RIGHT_EYE_BOTTOM],
      landmarks[RIGHT_EYE_OUTER],
      landmarks[RIGHT_EYE_INNER],
    ],
  ];
  const ratios: number[] = [];
  for (const [top, bottom, outer, inner] of pairs) {
    if (!top || !bottom || !outer || !inner) continue;
    const vertical = dist(top, bottom);
    const horizontal = dist(outer, inner);
    if (horizontal < 1e-6) continue;
    ratios.push(vertical / horizontal);
  }
  if (ratios.length === 0) return 0.25;
  return ratios.reduce((sum, r) => sum + r, 0) / ratios.length;
}

/**
 * Mouth openness: vertical lip opening over mouth width. Sustained openness
 * (not a split-second shape change) reads as talking → the `speaking` signal.
 */
export function mouthOpenness(landmarks: Landmark[]): number {
  const left = landmarks[MOUTH_LEFT];
  const right = landmarks[MOUTH_RIGHT];
  const top = landmarks[MOUTH_TOP];
  const bottom = landmarks[MOUTH_BOTTOM];
  if (!left || !right || !top || !bottom) return 0;
  const width = dist(left, right);
  if (width < 1e-6) return 0;
  return dist(top, bottom) / width;
}

/**
 * Variance of the Laplacian over a grayscale frame: the classic blur metric.
 * A sharp image has strong second-derivative energy (high variance); a blurry
 * one collapses toward zero. `pixels` is row-major grayscale, 0..255.
 */
export function laplacianVariance(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
): number {
  if (width < 3 || height < 3) return 0;
  let sum = 0;
  let sumSq = 0;
  let count = 0;
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x;
      const lap =
        pixels[i - 1] + pixels[i + 1] + pixels[i - width] + pixels[i + width] - 4 * pixels[i];
      sum += lap;
      sumSq += lap * lap;
      count++;
    }
  }
  if (count === 0) return 0;
  const mean = sum / count;
  return sumSq / count - mean * mean;
}

/** One frame of detections handed to the classifier. */
export interface FrameInput {
  timestampMs: number;
  /** Per-face landmark arrays (empty array = no face detected). */
  faces: Landmark[][];
  /** Optional blur metric for this frame (variance of Laplacian). */
  blurVariance?: number;
  config?: SignalConfig;
}

/**
 * Update episode state from one frame and return any signals that just fired.
 *
 * A signal fires when its condition holds continuously for `minActiveMs` and
 * the previous fire is outside `cooldownMs` — this debounces single-frame
 * noise (a blink is not `eyes_closed`; a glance is not `looking_away`).
 */
export function classifyFrame(state: SignalState, input: FrameInput): ProctorObservation[] {
  const config = input.config ?? DEFAULT_CONFIG;
  const { timestampMs, faces, blurVariance } = input;
  const observations: ProctorObservation[] = [];

  const primary = faces[0];
  const box = primary ? faceBox(primary) : null;
  const faceIsBigEnough = box !== null && box.width >= config.minFaceWidth;

  // --- per-signal condition for this frame --------------------------------
  const yaw = primary && faceIsBigEnough ? estimateYaw(primary) : 0;
  const pitch = primary && faceIsBigEnough ? estimatePitch(primary) : 0;
  const conditions: Partial<Record<ProctorSignal, Record<string, string | number | boolean>>> = {};

  if (faces.length === 0) {
    conditions.no_face = {};
  } else if (faces.length >= 2) {
    conditions.multiple_faces = { faces: faces.length };
  }

  if (faceIsBigEnough) {
    if (Math.abs(yaw) > config.lookingAway.yawThreshold) {
      conditions.looking_away = { direction: yaw > 0 ? "left" : "right", yaw: round2(yaw) };
    } else if (pitch > 0.75) {
      // Looking down at a desk/phone is also "not at the screen".
      conditions.looking_away = { direction: "down", pitch: round2(pitch) };
    }
    if (eyeAspectRatio(primary) < config.eyesClosed.earThreshold) {
      conditions.eyes_closed = {};
    }
    if (mouthOpenness(primary) > config.speaking.opennessThreshold) {
      conditions.speaking = {};
    }
  }

  if (blurVariance !== undefined && blurVariance < config.videoBlur.varianceThreshold) {
    conditions.video_blur = { variance: Math.round(blurVariance) };
  }

  // --- episode bookkeeping ------------------------------------------------
  for (const signal of ALL_SIGNALS) {
    const cfg = configFor(config, signal);
    const active = conditions[signal] !== undefined;
    if (active) {
      if (state.activeSince[signal] === undefined) {
        state.activeSince[signal] = timestampMs;
      }
      const since = state.activeSince[signal]!;
      const heldMs = timestampMs - since;
      const last = state.lastFired[signal];
      if (
        heldMs >= cfg.minActiveMs &&
        (last === undefined || timestampMs - last >= cfg.cooldownMs)
      ) {
        state.lastFired[signal] = timestampMs;
        observations.push({
          signal,
          duration_s: round1(heldMs / 1000),
          detail: conditions[signal],
        });
      }
    } else {
      delete state.activeSince[signal];
    }
  }

  return observations;
}

const ALL_SIGNALS: ProctorSignal[] = [
  "looking_away",
  "no_face",
  "multiple_faces",
  "speaking",
  "eyes_closed",
  "video_blur",
];

function configFor(
  config: SignalConfig,
  signal: ProctorSignal,
): { minActiveMs: number; cooldownMs: number } {
  switch (signal) {
    case "looking_away":
      return config.lookingAway;
    case "no_face":
      return config.noFace;
    case "multiple_faces":
      return config.multipleFaces;
    case "speaking":
      return config.speaking;
    case "eyes_closed":
      return config.eyesClosed;
    case "video_blur":
      return config.videoBlur;
    default:
      return { minActiveMs: 0, cooldownMs: 0 };
  }
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
