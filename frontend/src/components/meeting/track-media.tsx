"use client";

import * as React from "react";
import type { Track } from "livekit-client";

import { cn } from "cn";

/** Renders a LiveKit track onto a media element and detaches it on cleanup. */
function useAttach(track: Track, kind: "video" | "audio") {
  const ref = React.useRef<(HTMLVideoElement & HTMLAudioElement) | null>(null);

  React.useEffect(() => {
    const element = ref.current;
    if (!element) return;
    track.attach(element);
    return () => {
      track.detach(element);
    };
  }, [track, kind]);

  return ref;
}

function TrackVideo({
  track,
  mirrored = false,
  className,
}: {
  track: Track;
  mirrored?: boolean;
  className?: string;
}) {
  const ref = useAttach(track, "video");
  return (
    <video
      ref={ref}
      autoPlay
      playsInline
      muted={mirrored}
      className={cn("h-full w-full object-cover", mirrored && "scale-x-[-1]", className)}
    />
  );
}

function TrackAudio({ track }: { track: Track }) {
  const ref = useAttach(track, "audio");
  return <audio ref={ref} autoPlay />;
}

export { TrackAudio, TrackVideo };
