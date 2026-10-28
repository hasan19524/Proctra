"use client";

import * as React from "react";

import {
  MicIcon,
  MicOffIcon,
  VideoIcon,
  VideoOffIcon,
  ClipboardCopyIcon,
  ShieldCheckIcon,
  ShieldAlertIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { toast } from "@/components/ui/toast";
import { runSelfCheck, type SelfCheckResult } from "@/hooks/use-proctoring";
import { cn } from "cn";

export interface JoinOptions {
  displayName: string;
  micOn: boolean;
  cameraOn: boolean;
  password?: string;
}

interface PreJoinLobbyProps {
  code: string;
  title?: string | null;
  defaultName: string;
  /** Phase 16 — exam mode: shows the proctoring notice + self-check. */
  isExam?: boolean;
  proctoringEnabled?: boolean;
  /** Hosts bypass the password server-side, so the UI must not demand it. */
  isHost?: boolean;
  onJoin: (options: JoinOptions) => void;
}

type MediaState = "acquiring" | "live" | "unavailable";

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.charAt(0) ?? "";
  const second = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? "") : "";
  return (first + second).toUpperCase() || "?";
}

/** Pre-join lobby: real camera/mic preview with toggles before entering the meet. */
export function PreJoinLobby({
  code,
  title,
  defaultName,
  isExam = false,
  proctoringEnabled = false,
  isHost = false,
  onJoin,
}: PreJoinLobbyProps) {
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);

  const [displayName, setDisplayName] = React.useState(defaultName);
  const [micOn, setMicOn] = React.useState(true);
  const [cameraOn, setCameraOn] = React.useState(true);
  const [password, setPassword] = React.useState("");
  const [mediaState, setMediaState] = React.useState<MediaState>("acquiring");
  const [selfCheck, setSelfCheck] = React.useState<SelfCheckResult | null>(null);
  const [selfCheckRunning, setSelfCheckRunning] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    const media = navigator.mediaDevices;

    if (!media?.getUserMedia) {
      queueMicrotask(() => {
        if (!cancelled) setMediaState("unavailable");
      });
      return;
    }

    media
      .getUserMedia({ audio: true, video: true })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setMediaState("live");
      })
      .catch(() => {
        if (!cancelled) setMediaState("unavailable");
      });

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  React.useEffect(() => {
    const stream = streamRef.current;
    if (!stream) return;
    stream.getAudioTracks().forEach((track) => {
      track.enabled = micOn;
    });
    stream.getVideoTracks().forEach((track) => {
      track.enabled = cameraOn;
    });
  }, [micOn, cameraOn]);

  const previewLive = cameraOn && mediaState === "live";

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      toast.add({ type: "success", title: "Invite code copied" });
    } catch {
      toast.add({ type: "error", title: "Couldn't copy the code" });
    }
  };

  const runCheck = React.useCallback(async () => {
    setSelfCheckRunning(true);
    setSelfCheck(null);
    try {
      const result = await runSelfCheck(2200);
      setSelfCheck(result);
      if (result.ok) {
        toast.add({ type: "success", title: "Camera check passed" });
      }
    } catch {
      setSelfCheck({
        ok: false,
        faceDetected: false,
        issues: ["Something went wrong during the camera check. Please retry."],
        blurVariance: null,
      });
    } finally {
      setSelfCheckRunning(false);
    }
  }, []);

  const isExamRoom = isExam && proctoringEnabled;
  // The proctoring card is student-facing: the host is never proctored.
  const showExamNotice = isExamRoom && !isHost;
  const canJoin =
    displayName.trim() &&
    // Exam meetings always have a password (server-enforced); the host
    // bypasses it server-side, so only non-hosts must fill it in.
    (!isExam || isHost || password.trim().length > 0);

  return (
    <div className="bg-background text-foreground flex h-svh flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg"
          >
            <VideoIcon />
          </span>
          <span className="font-heading hidden text-lg font-semibold tracking-tight sm:block">
            Procto
          </span>
          {isExamRoom ? (
            <span className="bg-warning/10 text-warning flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium">
              <ShieldCheckIcon className="size-3.5" aria-hidden="true" />
              Exam
            </span>
          ) : null}
        </div>

        <button
          type="button"
          onClick={() => void copyCode()}
          className="border-input bg-muted/60 hover:bg-muted flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-medium transition-colors"
          aria-label={`Copy invite code ${code}`}
        >
          {code}
          <ClipboardCopyIcon className="text-muted-foreground size-4" aria-hidden="true" />
        </button>

        <span className="w-9" aria-hidden="true" />
      </header>

      <main className="flex min-h-0 flex-1 flex-col items-center justify-center gap-5 px-4 py-6">
        <div className="w-full max-w-3xl">
          <h1 className="font-heading mb-1 text-center text-xl font-medium sm:text-2xl">
            {title ?? "Ready to join?"}
          </h1>
          <p className="text-muted-foreground mb-4 text-center text-sm">
            {showExamNotice
              ? "This is a proctored exam. Your camera will be analyzed locally — no video leaves your device."
              : "Check your camera and microphone before you join."}
          </p>

          {/* Phase 16 — exam notice + self-check card. */}
          {showExamNotice ? (
            <div className="border-warning/30 bg-warning/5 mb-4 rounded-xl border p-4">
              <div className="flex items-start gap-3">
                <ShieldCheckIcon
                  className="text-warning mt-0.5 size-5 shrink-0"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <h2 className="text-sm font-semibold">AI proctoring is enabled</h2>
                  <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                    A vision model running in your browser watches for looking away, leaving the
                    exam tab, other people in frame, and similar signals. All analysis happens
                    locally — only the signal labels are sent to the host, never your video.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void runCheck()}
                      disabled={selfCheckRunning || !cameraOn}
                      className="rounded-full"
                    >
                      {selfCheckRunning ? (
                        <>
                          <Spinner className="size-3.5" />
                          Checking…
                        </>
                      ) : (
                        "Run camera check"
                      )}
                    </Button>
                    {selfCheck ? (
                      selfCheck.ok ? (
                        <span className="text-success flex items-center gap-1 text-xs font-medium">
                          <ShieldCheckIcon className="size-3.5" aria-hidden="true" />
                          Face detected — you&apos;re good to go
                        </span>
                      ) : (
                        <span className="text-destructive flex items-center gap-1 text-xs font-medium">
                          <ShieldAlertIcon className="size-3.5" aria-hidden="true" />
                          {selfCheck.issues[0] ?? "Check failed"}
                        </span>
                      )
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="relative aspect-video w-full overflow-hidden rounded-2xl bg-zinc-950">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              aria-label="Camera preview"
              className={cn(
                "h-full w-full scale-x-[-1] object-cover transition-opacity",
                previewLive ? "opacity-100" : "opacity-0",
              )}
            />

            {!previewLive && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <span className="bg-accent text-primary-foreground ring-primary/40 flex size-20 items-center justify-center rounded-full text-2xl font-medium ring-2">
                  {initialsOf(displayName || "?")}
                </span>
                <p className="text-sm text-zinc-400">
                  {mediaState === "acquiring"
                    ? "Starting camera…"
                    : cameraOn
                      ? "Camera unavailable — check browser permissions"
                      : "Camera is off"}
                </p>
              </div>
            )}

            {mediaState === "acquiring" && previewLive === false && (
              <div className="absolute top-3 left-3">
                <Spinner className="size-4 text-zinc-400" />
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-center gap-3">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={micOn ? "Turn off microphone" : "Turn on microphone"}
              aria-pressed={!micOn}
              onClick={() => setMicOn((on) => !on)}
              className={cn(
                "rounded-full",
                !micOn &&
                  "bg-destructive text-destructive-foreground hover:bg-destructive/90 border-transparent",
              )}
            >
              {micOn ? <MicIcon /> : <MicOffIcon />}
            </Button>

            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={cameraOn ? "Turn off camera" : "Turn on camera"}
              aria-pressed={!cameraOn}
              onClick={() => setCameraOn((on) => !on)}
              className={cn(
                "rounded-full",
                !cameraOn &&
                  "bg-destructive text-destructive-foreground hover:bg-destructive/90 border-transparent",
              )}
            >
              {cameraOn ? <VideoIcon /> : <VideoOffIcon />}
            </Button>
          </div>

          <div className="mx-auto mt-4 max-w-sm">
            <Input
              aria-label="Your name"
              placeholder="Your name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="h-10 rounded-full px-4 text-center"
            />
          </div>

          <div className="mx-auto mt-3 max-w-sm">
            <Input
              type="password"
              aria-label="Meeting password"
              placeholder={
                isExam
                  ? isHost
                    ? "Exam password (not needed for you)"
                    : "Exam password (required)"
                  : "Meeting password (if required)"
              }
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-10 rounded-full px-4 text-center"
              autoComplete="off"
              required={isExam && !isHost}
            />
          </div>

          <div className="mt-5 flex justify-center">
            <Button
              type="button"
              variant="success"
              disabled={!canJoin}
              onClick={() =>
                onJoin({
                  displayName: displayName.trim(),
                  micOn,
                  cameraOn,
                  password: password.trim() || undefined,
                })
              }
              className="rounded-full px-8"
            >
              <VideoIcon data-icon="inline-start" />
              {isExamRoom && !isHost ? "Join exam" : "Join now"}
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
