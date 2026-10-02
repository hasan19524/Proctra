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

const MEET_CODE = "ktq-vxm-pnz";

const PARTICIPANTS: PanelParticipant[] = [
  { id: "you", name: "Hasan", role: "Meeting host", isMuted: false, isYou: true },
  { id: "amina", name: "Amina Yusuf", role: "Contributor" },
  { id: "carlos", name: "Carlos Mendes", role: "Contributor", isMuted: true },
  { id: "priya", name: "Priya Nair", role: "Contributor" },
];

function RoomPage() {
  const now = useClock();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const [state, setState] = React.useState({
    isMicOn: true,
    isCameraOn: true,
    isScreenSharing: false,
    isHandRaised: false,
  });
  const [isReactionsOpen, setReactionsOpen] = React.useState(false);
  const [panel, setPanel] = React.useState<"people" | "chat" | null>(null);
  const [isLocked, setLocked] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);

  const demo = React.useCallback((message: string) => {
    toast.add({ type: "info", title: message });
  }, []);

  const togglePanel = React.useCallback((next: "people" | "chat") => {
    setPanel((current) => (current === next ? null : next));
  }, []);

  return (
    <div className="bg-background text-foreground relative flex h-svh flex-col">
      <MeetingTopBar
        code={MEET_CODE}
        time={time}
        participantCount={PARTICIPANTS.length}
        onShowDetails={() => demo("Meeting details (demo)")}
        onOpenPeople={() => togglePanel("people")}
      />

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <main className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <ParticipantTile
              name="Hasan (You)"
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
              onLeave={() => demo("You left the meet (demo)")}
            />
          </footer>
        </main>

        {panel === "people" ? (
          <div className="w-96 max-w-full shrink-0">
            <PeoplePanel
              participants={PARTICIPANTS}
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
                    author: "Hasan",
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

export default RoomPage;
