"use client";

import * as React from "react";

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
    isRemoved,
    selfMuteNonce,
    updateFlags,
    sendChat,
    sendHostAction,
  } = useMeetingWs(code);

  // Host muted me: turn the mic off locally (render-phase adjustment, the
  // documented React pattern for deriving state from a prop/event).
  if (selfMuteNonce > handledMuteNonce) {
    setHandledMuteNonce(selfMuteNonce);
    setIsMicOn(false);
  }

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
      onSendChat={sendChat}
      onHostAction={sendHostAction}
      micOn={isMicOn}
      cameraOn={isCameraOn}
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
