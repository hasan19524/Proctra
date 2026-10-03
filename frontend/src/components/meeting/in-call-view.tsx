"use client";

import * as React from "react";

import { toast } from "@/components/ui/toast";
import { useClock } from "@/hooks/use-clock";
import type { MediaTile } from "@/hooks/use-livekit-room";
import type {
  MeetingMeta,
  NoteVisibility,
  WsChatMessage,
  WsNote,
  WsParticipant,
  WsReaction,
} from "@/hooks/use-meeting-ws";
import type { WsStatus } from "@/lib/ws";
import { MeetingControls, UtilityCluster } from "@/components/meeting/meeting-controls";
import {
  ChatPanel,
  NotesPanel,
  PeoplePanel,
  type ChatMessage,
  type PanelParticipant,
} from "@/components/meeting/meeting-panels";
import { ParticipantTile } from "@/components/meeting/participant-tile";
import { ReactionBar, REACTIONS } from "@/components/meeting/reaction-bar";
import { MeetingTopBar } from "@/components/meeting/meeting-top-bar";
import { TrackAudio, TrackVideo } from "@/components/meeting/track-media";
import type { MeetingStatus } from "@/components/meeting/status-indicator";

interface InCallViewProps {
  code: string;
  displayName: string;
  participants: WsParticipant[];
  selfUserId: string | null;
  connection: WsStatus;
  messages: WsChatMessage[];
  meeting: MeetingMeta | null;
  notes: WsNote[];
  reactions: WsReaction[];
  mediaTiles?: MediaTile[];
  onSendChat: (body: string) => string | null;
  onSendNote: (visibility: NoteVisibility, text: string) => string | null;
  onSendReaction: (label: string) => string | null;
  onHostAction: (action: string, payload?: Record<string, unknown>) => void;
  micOn: boolean;
  cameraOn: boolean;
  isHandRaised: boolean;
  onToggleHand: () => void;
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onLeave: () => void;
}

function toPanelMessage(message: WsChatMessage): ChatMessage {
  const time = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  return {
    id: message.id,
    author: message.sender_name,
    text: message.body,
    time,
  };
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
  messages,
  meeting,
  notes,
  reactions,
  mediaTiles = [],
  onSendChat,
  onSendNote,
  onSendReaction,
  onHostAction,
  micOn,
  cameraOn,
  isHandRaised,
  onToggleHand,
  onToggleMic,
  onToggleCamera,
  onLeave,
}: InCallViewProps) {
  const now = useClock();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const [state, setState] = React.useState({
    isScreenSharing: false,
  });
  const [isReactionsOpen, setReactionsOpen] = React.useState(false);
  const [panel, setPanel] = React.useState<"people" | "chat" | "notes" | null>(null);

  const isLocked = meeting?.is_locked ?? false;
  const allowChat = meeting?.allow_chat ?? true;
  const allowReactions = meeting?.allow_reactions ?? true;

  const self = React.useMemo(
    () => participants.find((participant) => participant.user_id === selfUserId) ?? null,
    [participants, selfUserId],
  );
  const isSelfHost = self?.is_host ?? false;
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

  const videoFor = (tile: MediaTile | undefined): React.ReactNode =>
    tile?.cameraTrack ? <TrackVideo track={tile.cameraTrack} mirrored={tile.isLocal} /> : null;

  const localTile = mediaTiles.find((tile) => tile.isLocal);

  const togglePanel = React.useCallback((next: "people" | "chat" | "notes") => {
    setPanel((current) => (current === next ? null : next));
  }, []);

  return (
    <div className="bg-background text-foreground relative flex h-svh flex-col">
      {mediaTiles.map((tile) =>
        tile.isLocal || !tile.audioTrack ? null : (
          <TrackAudio key={tile.id} track={tile.audioTrack} />
        ),
      )}
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
              isHandRaised={isHandRaised}
              isHost={self?.is_host ?? true}
              connection="excellent"
              media={videoFor(localTile)}
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
                  media={videoFor(
                    mediaTiles.find((tile) => tile.id === participant.user_id && !tile.isLocal),
                  )}
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
            <FloatingReactions reactions={reactions} />
            {isReactionsOpen ? (
              <ReactionBar
                onReact={(label) => {
                  if (!allowReactions) {
                    toast.add({
                      type: "error",
                      title: "Reactions are turned off",
                      description: "The host turned off reactions for this meet.",
                    });
                    setReactionsOpen(false);
                    return;
                  }
                  if (!onSendReaction(label)) {
                    toast.add({
                      type: "error",
                      title: "Reaction not sent",
                      description: "You are not connected — it will send after reconnect.",
                    });
                  }
                }}
                onCollapse={() => setReactionsOpen(false)}
              />
            ) : null}
            <MeetingControls
              state={{
                isMicOn: micOn,
                isCameraOn: cameraOn,
                isScreenSharing: state.isScreenSharing,
                isHandRaised,
              }}
              isReactionsOpen={isReactionsOpen}
              onToggleMic={onToggleMic}
              onToggleCamera={onToggleCamera}
              onToggleScreenShare={() =>
                setState((s) => ({ ...s, isScreenSharing: !s.isScreenSharing }))
              }
              onToggleHand={onToggleHand}
              onOpenChat={() => togglePanel("chat")}
              onToggleReactions={() => setReactionsOpen((open) => !open)}
              onMoreAction={(action) => {
                if (action === "notes") {
                  togglePanel("notes");
                  return;
                }
                demo(`${action} (demo)`);
              }}
              onLeave={onLeave}
            />
          </footer>
        </main>

        {panel === "people" ? (
          <div className="w-96 max-w-full shrink-0">
            <PeoplePanel
              participants={panelParticipants}
              canManage={isSelfHost}
              onMute={(id) => onHostAction("mute_participant", { target_id: id })}
              onRemove={(id) => onHostAction("remove", { target_id: id })}
              onAddPeople={() => demo("Invite people (demo)")}
              onClose={() => setPanel(null)}
              className="h-full"
            />
          </div>
        ) : null}

        {panel === "notes" ? (
          <div className="w-96 max-w-full shrink-0">
            <NotesPanel
              notes={notes}
              isHost={isSelfHost}
              connectionOpen={connection === "open"}
              onClose={() => setPanel(null)}
              onSave={(visibility, text) => {
                const sent = onSendNote(visibility, text);
                if (!sent) {
                  toast.add({
                    type: "error",
                    title: "Note not saved",
                    description: "You are not connected — it will fail until the call reconnects.",
                  });
                  return false;
                }
                return true;
              }}
              className="h-full"
            />
          </div>
        ) : null}

        {panel === "chat" ? (
          <div className="w-96 max-w-full shrink-0">
            <ChatPanel
              messages={messages.map(toPanelMessage)}
              allowChat={allowChat}
              canManage={isSelfHost}
              onToggleAllowChat={(enabled) =>
                onHostAction("set_permissions", { allow_chat: enabled })
              }
              onClose={() => setPanel(null)}
              onSend={(text) => {
                if (!allowChat) {
                  toast.add({
                    type: "error",
                    title: "Chat is turned off",
                    description: "The host turned off chat for this meet.",
                  });
                  return;
                }
                if (!onSendChat(text)) {
                  toast.add({
                    type: "error",
                    title: "Message not sent",
                    description: "You are not connected — it will fail until the call reconnects.",
                  });
                }
              }}
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
          if (!isSelfHost) {
            demo("Only the host can lock the meet");
            return;
          }
          onHostAction(isLocked ? "unlock" : "lock");
        }}
      />
    </div>
  );
}

function FloatingReactions({ reactions }: { reactions: WsReaction[] }) {
  if (reactions.length === 0) return null;
  return (
    <div
      aria-label="Reactions"
      aria-live="polite"
      className="pointer-events-none absolute inset-x-0 bottom-28 z-10 flex items-end justify-center gap-4"
    >
      {reactions.map((reaction, index) => (
        <div
          key={reaction.id}
          className="reaction-float flex flex-col items-center"
          style={{ animationDelay: `${(index % 4) * 150}ms` }}
        >
          <span className="text-4xl" aria-hidden="true">
            {REACTIONS.find((item) => item.label === reaction.label)?.emoji ?? "👍"}
          </span>
          <span className="bg-card/80 text-muted-foreground rounded-full px-2 py-0.5 text-xs">
            {reaction.name}
          </span>
        </div>
      ))}
    </div>
  );
}

export { FloatingReactions };
