/**
 * Proctoring signal types and scoring labels (Phase 16 — exam mode).
 *
 * Mirrors the server's closed set in `backend/app/models/proctor.py`. The
 * client only *names* observations; points are always assigned server-side.
 */

export type ProctorSignal =
  | "looking_away"
  | "no_face"
  | "multiple_faces"
  | "speaking"
  | "eyes_closed"
  | "tab_hidden"
  | "video_blur";

export const SIGNAL_LABELS: Record<ProctorSignal, string> = {
  looking_away: "looking away",
  no_face: "no face in frame",
  multiple_faces: "second person in frame",
  speaking: "speaking",
  eyes_closed: "eyes closed",
  tab_hidden: "left the exam tab",
  video_blur: "blurry video",
};

/** One observation emitted by the engine (sent as a `proctor.event` frame). */
export interface ProctorObservation {
  signal: ProctorSignal;
  /** How long the condition held before we reported it, in seconds. */
  duration_s: number;
  detail?: Record<string, string | number | boolean>;
}

export type ProctorStatus =
  | "idle"
  | "loading"
  | "active"
  /** Running, but degraded (blurry video, camera off, tab hidden). */
  | "degraded"
  /** Failed to start (model load error, no camera). Retryable. */
  | "error";

export interface ProctorStatusInfo {
  status: ProctorStatus;
  /** User-facing explanation when status is degraded/error. */
  message?: string;
}
