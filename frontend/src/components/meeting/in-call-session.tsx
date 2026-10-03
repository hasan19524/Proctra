"use client";

import * as React from "react";

import { toast } from "@/components/ui/toast";
import { useLiveKitRoom } from "@/hooks/use-livekit-room";
import { useMeetingWs } from "@/hooks/use-meeting-ws";
import { InCallView } from "@/components/meeting/in-call-view";
import { Button } from "@/components/ui/button";

interface InCallSessionProps {
  code: string;
  displayName: string;
  micOn: boolean;
  cameraOn: boolean;
  onLeave: () => void;
}

/**
 * Connects the meeting WebSocket and hands live state to `InCallView`:
 * roster + connection status from the socket, mic/camera flags pushed via
 * `presence.update` whenever they change (or after every reconnect, since the
 * server rebuilds presence on rejoin). Also renders terminal states — removed
 * by the host or the meet having ended — instead of the call shell.
 */
export function InCallSession({ code, displayName, micOn, cameraOn, onLeave }: InCallSessionProps) {
  const [isMicOn, setIsMicOn] = React.useState(micOn);
  const [isCameraOn, setIsCameraOn] = React.useState(cameraOn);
  const [handledMuteNonce, setHandledMuteNonce] = React.useState(0);

  const {
    status,
    participants,
    selfUserId,
    messages,
    meeting,
    notes,
    reactions,
    isRemoved,
    selfMuteNonce,
    updateFlags,
    sendChat,
    sendHostAction,
    sendNoteSave,
    sendReaction,
  } = useMeetingWs(code);

  // Hand raise is server state: the flag round-trips through presence so
  // everyone (including a reconnecting you) sees the same hand.
  const self = participants.find((participant) => participant.user_id === selfUserId) ?? null;
  const isHandRaised = self?.hand_raised ?? false;

  // Media (LiveKit SFU) runs beside the app WS: roster on one socket, real
  // audio/video on the SFU. A media failure degrades to chat-only. Flags are
  // the local state (not the entry props) so toggles reach LiveKit too.
  const media = useLiveKitRoom(code, isMicOn, isCameraOn);
  const mediaStatusRef = React.useRef(media.status);
  React.useEffect(() => {
    if (media.status === "failed" && mediaStatusRef.current !== "failed") {
      toast.add({
        type: "warning",
        title: "Live media unavailable",
        description: "Video and audio could not connect — chat and notes still work.",
      });
    }
    mediaStatusRef.current = media.status;
  }, [media.status]);

  // Host muted me: turn the mic off locally (render-phase adjustment, the
  // documented React pattern for deriving state from a prop/event).
  if (selfMuteNonce > handledMuteNonce) {
    setHandledMuteNonce(selfMuteNonce);
    setIsMicOn(false);
  }

  const allowScreenShare = meeting?.allow_screen_share ?? true;
  const { screenShareOn, toggleScreenShare } = media;

  const handleToggleScreenShare = React.useCallback(async () => {
    if (!allowScreenShare) {
      toast.add({
        type: "error",
        title: "Screen sharing is turned off",
        description: "The host turned off screen sharing for this meet.",
      });
      return;
    }
    const next = await toggleScreenShare();
    if (next === null) {
      toast.add({
        type: "warning",
        title: "Screen share cancelled",
        description: "Your screen was not shared.",
      });
      return;
    }
    updateFlags({ screen_share_on: next });
  }, [allowScreenShare, toggleScreenShare, updateFlags]);

  // Host disabled screen sharing mid-share: stop the local publication so the
  // permission means something (the server also rejects the roster flag).
  // Fires at most once per disable — the effect re-runs on unrelated renders.
  const forceStoppedRef = React.useRef(false);
  React.useEffect(() => {
    if (allowScreenShare) {
      forceStoppedRef.current = false;
      return;
    }
    if (!screenShareOn || forceStoppedRef.current) return;
    forceStoppedRef.current = true;
    void toggleScreenShare().then((next) => {
      if (next !== null) updateFlags({ screen_share_on: false });
    });
    toast.add({
      type: "info",
      title: "Screen sharing turned off",
      description: "The host turned off screen sharing for this meet.",
    });
  }, [allowScreenShare, screenShareOn, toggleScreenShare, updateFlags]);

  React.useEffect(() => {
    if (status !== "open") return;
    updateFlags({ mic_on: isMicOn, camera_on: isCameraOn });
  }, [status, isMicOn, isCameraOn, updateFlags]);

  if (isRemoved || meeting?.status === "ended") {
    return (
      <SessionNotice
        title={isRemoved ? "You were removed from the meet" : "This meet has ended"}
        description={
          isRemoved
            ? "The host removed you from this meeting."
            : "The host ended the meeting for everyone."
        }
        onAction={onLeave}
      />
    );
  }

  return (
    <InCallView
      code={code}
      displayName={displayName}
      participants={participants}
      selfUserId={selfUserId}
      connection={status}
      messages={messages}
      meeting={meeting}
      notes={notes}
      reactions={reactions}
      mediaTiles={media.tiles}
      onSendChat={sendChat}
      onSendNote={(visibility, text) => sendNoteSave(visibility, { text })}
      onSendReaction={sendReaction}
      onHostAction={sendHostAction}
      micOn={isMicOn}
      cameraOn={isCameraOn}
      isScreenSharing={screenShareOn}
      canScreenShare={allowScreenShare}
      onToggleScreenShare={() => void handleToggleScreenShare()}
      isHandRaised={isHandRaised}
      onToggleHand={() => updateFlags({ hand_raised: !isHandRaised })}
      onToggleMic={() => setIsMicOn((on) => !on)}
      onToggleCamera={() => setIsCameraOn((on) => !on)}
      onLeave={onLeave}
    />
  );
}

function SessionNotice({
  title,
  description,
  onAction,
}: {
  title: string;
  description: string;
  onAction: () => void;
}) {
  return (
    <main className="bg-background flex min-h-svh flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-muted-foreground max-w-sm text-sm">{description}</p>
      <Button onClick={onAction}>Back to home</Button>
    </main>
  );
}
