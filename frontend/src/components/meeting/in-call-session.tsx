"use client";

import * as React from "react";

import { useMeetingWs } from "@/hooks/use-meeting-ws";
import { InCallView } from "@/components/meeting/in-call-view";

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
 * server rebuilds presence on rejoin).
 */
export function InCallSession({ code, displayName, micOn, cameraOn, onLeave }: InCallSessionProps) {
  const [isMicOn, setIsMicOn] = React.useState(micOn);
  const [isCameraOn, setIsCameraOn] = React.useState(cameraOn);

  const { status, participants, selfUserId, messages, updateFlags, sendChat } = useMeetingWs(code);

  React.useEffect(() => {
    if (status !== "open") return;
    updateFlags({ mic_on: isMicOn, camera_on: isCameraOn });
  }, [status, isMicOn, isCameraOn, updateFlags]);

  return (
    <InCallView
      code={code}
      displayName={displayName}
      participants={participants}
      selfUserId={selfUserId}
      connection={status}
      messages={messages}
      onSendChat={sendChat}
      micOn={isMicOn}
      cameraOn={isCameraOn}
      onToggleMic={() => setIsMicOn((on) => !on)}
      onToggleCamera={() => setIsCameraOn((on) => !on)}
      onLeave={onLeave}
    />
  );
}
