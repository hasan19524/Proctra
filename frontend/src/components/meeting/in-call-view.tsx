"use client";

import * as React from "react";

import { toast } from "@/components/ui/toast";
import { useClock } from "@/hooks/use-clock";
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

interface InCallViewProps {
  code: string;
  displayName: string;
  micOn: boolean;
  cameraOn: boolean;
  onLeave: () => void;
}

function buildParticipants(youName: string): PanelParticipant[] {
  return [
    { id: "you", name: youName, role: "Meeting host", isMuted: false, isYou: true },
    { id: "amina", name: "Amina Yusuf", role: "Contributor" },
    { id: "carlos", name: "Carlos Mendes", role: "Contributor", isMuted: true },
    { id: "priya", name: "Priya Nair", role: "Contributor" },
  ];
}

/** The in-call shell: top bar, tiles, controls, panels (Phase 1 layout). */
export function InCallView({ code, displayName, micOn, cameraOn, onLeave }: InCallViewProps) {
  const now = useClock();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const [state, setState] = React.useState({
    isMicOn: micOn,
    isCameraOn: cameraOn,
    isScreenSharing: false,
    isHandRaised: false,
  });
  const [isReactionsOpen, setReactionsOpen] = React.useState(false);
  const [panel, setPanel] = React.useState<"people" | "chat" | null>(null);
  const [isLocked, setLocked] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);

  const participants = React.useMemo(() => buildParticipants(displayName), [displayName]);

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
        participantCount={participants.length}
        onShowDetails={() => demo("Meeting details (demo)")}
        onOpenPeople={() => togglePanel("people")}
      />

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <main className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <ParticipantTile
              name={`${displayName} (You)`}
              isMuted={!state.isMicOn}
              isCameraOff={!state.isCameraOn}
              isScreenSharing={state.isScreenSharing}
              isHost
              connection="excellent"
              className="h-full w-full"
            />
          </div>

          <div className="flex gap-2 overflow-x-auto pb-1">
            <ParticipantTile name="Amina Yusuf" isSpeaking connection="good" className="w-52" />
            <ParticipantTile
              name="Carlos Mendes"
              isMuted
              isCameraOff
              connection="fair"
              className="w-52"
            />
            <ParticipantTile
              name="Priya Nair"
              isHandRaised
              connection="excellent"
              className="w-52"
            />
          </div>

          <footer className="flex flex-col items-center gap-2 pb-1">
            {isReactionsOpen ? (
              <ReactionBar
                onReact={(label) => demo(`Reaction sent: ${label}`)}
                onCollapse={() => setReactionsOpen(false)}
              />
            ) : null}
            <MeetingControls
              state={state}
              isReactionsOpen={isReactionsOpen}
              onToggleMic={() => setState((s) => ({ ...s, isMicOn: !s.isMicOn }))}
              onToggleCamera={() => setState((s) => ({ ...s, isCameraOn: !s.isCameraOn }))}
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
              participants={participants}
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
