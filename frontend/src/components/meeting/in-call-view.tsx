"use client";

import * as React from "react";

import { toast } from "@/components/ui/toast";
import { useClock } from "@/hooks/use-clock";
import type { WsParticipant } from "@/hooks/use-meeting-ws";
import type { WsStatus } from "@/lib/ws";
import { MeetingControls, UtilityCluster } from "@/components/meeting/meeting-controls";
import {
  ChatPanel,
  PeoplePanel,
  type ChatMessage,
  type PanelParticipant,
} from "@/components/meeting/meeting-panels";
import { ParticipantTile } from "@/components/meeting/participant-tile";
import { ReactionBar } from "@/components/meeting/reaction-bar";
import { MeetingTopBar } from "@/components/meeting/meeting-top-bar";
import type { MeetingStatus } from "@/components/meeting/status-indicator";

interface InCallViewProps {
  code: string;
  displayName: string;
  participants: WsParticipant[];
  selfUserId: string | null;
  connection: WsStatus;
  micOn: boolean;
  cameraOn: boolean;
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onLeave: () => void;
}

function toTopBarStatus(status: WsStatus): MeetingStatus | undefined {
  if (status === "closed") return undefined;
  if (status === "open") return "connected";
  return status;
}

/** The in-call shell: top bar, tiles, controls, panels (Phase 1 layout). */
export function InCallView({
  code,
  displayName,
  participants,
  selfUserId,
  connection,
  micOn,
  cameraOn,
  onToggleMic,
  onToggleCamera,
  onLeave,
}: InCallViewProps) {
  const now = useClock();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const [state, setState] = React.useState({
    isScreenSharing: false,
    isHandRaised: false,
  });
  const [isReactionsOpen, setReactionsOpen] = React.useState(false);
  const [panel, setPanel] = React.useState<"people" | "chat" | null>(null);
  const [isLocked, setLocked] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);

  const self = React.useMemo(
    () => participants.find((participant) => participant.user_id === selfUserId) ?? null,
    [participants, selfUserId],
  );
  const others = React.useMemo(
    () => participants.filter((participant) => participant.user_id !== selfUserId),
    [participants, selfUserId],
  );

  const panelParticipants = React.useMemo<PanelParticipant[]>(
    () =>
      participants.map((participant) => ({
        id: participant.user_id,
        name: participant.name,
        role: participant.is_host ? "Meeting host" : "Contributor",
        isMuted: !participant.mic_on,
        isYou: participant.user_id === selfUserId,
      })),
    [participants, selfUserId],
  );

  const demo = React.useCallback((message: string) => {
    toast.add({ type: "info", title: message });
  }, []);

  const togglePanel = React.useCallback((next: "people" | "chat") => {
    setPanel((current) => (current === next ? null : next));
  }, []);

  return (
    <div className="bg-background text-foreground relative flex h-svh flex-col">
      <MeetingTopBar
        code={code}
        time={time}
        connection={toTopBarStatus(connection)}
        participantCount={participants.length}
        onShowDetails={() => demo("Meeting details (demo)")}
        onOpenPeople={() => togglePanel("people")}
      />

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <main className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <ParticipantTile
              name={`${self?.name ?? displayName} (You)`}
              isMuted={!micOn}
              isCameraOff={!cameraOn}
              isScreenSharing={state.isScreenSharing}
              isHost={self?.is_host ?? true}
              connection="excellent"
              className="h-full w-full"
            />
          </div>

          {others.length > 0 ? (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {others.map((participant) => (
                <ParticipantTile
                  key={participant.user_id}
                  name={participant.name}
                  isMuted={!participant.mic_on}
                  isCameraOff={!participant.camera_on}
                  isHandRaised={participant.hand_raised}
                  isHost={participant.is_host}
                  connection="excellent"
                  className="w-52"
                />
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-center text-xs">
              {connection === "open"
                ? `Waiting for others to join — share code ${code}`
                : "Waiting for connection…"}
            </p>
          )}

          <footer className="flex flex-col items-center gap-2 pb-1">
            {isReactionsOpen ? (
              <ReactionBar
                onReact={(label) => demo(`Reaction sent: ${label}`)}
                onCollapse={() => setReactionsOpen(false)}
              />
            ) : null}
            <MeetingControls
              state={{
                isMicOn: micOn,
                isCameraOn: cameraOn,
                isScreenSharing: state.isScreenSharing,
                isHandRaised: state.isHandRaised,
              }}
              isReactionsOpen={isReactionsOpen}
              onToggleMic={onToggleMic}
              onToggleCamera={onToggleCamera}
              onToggleScreenShare={() =>
                setState((s) => ({ ...s, isScreenSharing: !s.isScreenSharing }))
              }
              onToggleHand={() => setState((s) => ({ ...s, isHandRaised: !s.isHandRaised }))}
              onOpenChat={() => togglePanel("chat")}
              onToggleReactions={() => setReactionsOpen((open) => !open)}
              onMoreAction={(action) => demo(`${action} (demo)`)}
              onLeave={onLeave}
            />
          </footer>
        </main>

        {panel === "people" ? (
          <div className="w-96 max-w-full shrink-0">
            <PeoplePanel
              participants={panelParticipants}
              onAddPeople={() => demo("Invite people (demo)")}
              onClose={() => setPanel(null)}
              className="h-full"
            />
          </div>
        ) : null}

        {panel === "chat" ? (
          <div className="w-96 max-w-full shrink-0">
            <ChatPanel
              messages={messages}
              onClose={() => setPanel(null)}
              onSend={(text) =>
                setMessages((current) => [
                  ...current,
                  {
                    id: `${current.length + 1}`,
                    author: displayName,
                    text,
                    time,
                  },
                ])
              }
              className="h-full"
            />
          </div>
        ) : null}
      </div>

      <UtilityCluster
        className="absolute right-3 bottom-3"
        isChatOpen={panel === "chat"}
        isPeopleOpen={panel === "people"}
        isHostControlsOn={isLocked}
        onOpenChat={() => togglePanel("chat")}
        onOpenPeople={() => togglePanel("people")}
        onToggleHostControls={() => {
          setLocked((locked) => !locked);
          demo(isLocked ? "Host controls unlocked (demo)" : "Host controls locked (demo)");
        }}
      />
    </div>
  );
}
