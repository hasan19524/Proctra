"use client";

import * as React from "react";

import { MicIcon, MicOffIcon, VideoIcon, VideoOffIcon, ClipboardCopyIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { toast } from "@/components/ui/toast";
import { cn } from "cn";

export interface JoinOptions {
  displayName: string;
  micOn: boolean;
  cameraOn: boolean;
}

interface PreJoinLobbyProps {
  code: string;
  title?: string | null;
  defaultName: string;
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
export function PreJoinLobby({ code, title, defaultName, onJoin }: PreJoinLobbyProps) {
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);

  const [displayName, setDisplayName] = React.useState(defaultName);
  const [micOn, setMicOn] = React.useState(true);
  const [cameraOn, setCameraOn] = React.useState(true);
  const [mediaState, setMediaState] = React.useState<MediaState>("acquiring");

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
            Check your camera and microphone before you join.
          </p>

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

          <div className="mt-5 flex justify-center">
            <Button
              type="button"
              variant="success"
              disabled={!displayName.trim()}
              onClick={() =>
                onJoin({
                  displayName: displayName.trim(),
                  micOn,
                  cameraOn,
                })
              }
              className="rounded-full px-8"
            >
              <VideoIcon data-icon="inline-start" />
              Join now
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
