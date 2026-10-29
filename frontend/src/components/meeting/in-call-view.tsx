"use client";

import * as React from "react";

import { toast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { ShieldAlertIcon } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useClock } from "@/hooks/use-clock";
import type { MediaTile } from "@/hooks/use-livekit-room";
import type {
  MeetingMeta,
  NoteVisibility,
  ProctorFlag,
  WsChatMessage,
  WsNote,
  WsParticipant,
  WsReaction,
} from "@/hooks/use-meeting-ws";
import type { WsStatus } from "@/lib/ws";
import { shareOrCopyLink } from "@/lib/share";
import { MeetingControls, UtilityCluster } from "@/components/meeting/meeting-controls";
import {
  ChatPanel,
  NotesPanel,
  PeoplePanel,
  type ChatMessage,
  type PanelParticipant,
} from "@/components/meeting/meeting-panels";
import { IntegrityPanel, StudentProctorChip } from "@/components/meeting/proctor-panel";
import { ParticipantTile } from "@/components/meeting/participant-tile";
import { ReactionBar, REACTIONS } from "@/components/meeting/reaction-bar";
import { MeetingTopBar } from "@/components/meeting/meeting-top-bar";
import { TrackAudio, TrackVideo } from "@/components/meeting/track-media";
import type { MeetingStatus } from "@/components/meeting/status-indicator";
import type { ProctorStatus } from "@/lib/proctor/types";

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
  speakingIds?: string[];
  pendingJoins?: Array<{ user_id: string; name: string }>;
  onApproveJoin?: (userId: string) => void;
  onRejectJoin?: (userId: string) => void;
  onSendChat: (body: string) => string | null;
  onSendNote: (visibility: NoteVisibility, text: string) => string | null;
  onSendReaction: (label: string) => string | null;
  onHostAction: (action: string, payload?: Record<string, unknown>) => void;
  micOn: boolean;
  cameraOn: boolean;
  isScreenSharing?: boolean;
  canScreenShare?: boolean;
  onToggleScreenShare?: () => void;
  isHandRaised: boolean;
  onToggleHand: () => void;
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onLeave: () => void;
  /** Phase 16 — exam mode. */
  isExam?: boolean;
  isHost?: boolean;
  proctorFlags?: ProctorFlag[];
  proctorStatus?: ProctorStatus;
  proctorMessage?: string | null;
  onRetryProctoring?: () => void;
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
  speakingIds = [],
  pendingJoins = [],
  onApproveJoin,
  onRejectJoin,
  onSendChat,
  onSendNote,
  onSendReaction,
  onHostAction,
  micOn,
  cameraOn,
  isScreenSharing = false,
  canScreenShare = true,
  onToggleScreenShare,
  isHandRaised,
  onToggleHand,
  onToggleMic,
  onToggleCamera,
  onLeave,
  isExam = false,
  isHost = false,
  proctorFlags = [],
  proctorStatus = "idle",
  proctorMessage = null,
  onRetryProctoring,
}: InCallViewProps) {
  const now = useClock();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const [isReactionsOpen, setReactionsOpen] = React.useState(false);
  const [panel, setPanel] = React.useState<"people" | "chat" | "notes" | "integrity" | null>(null);
  const [isDetailsOpen, setDetailsOpen] = React.useState(false);
  const [isEndOpen, setEndOpen] = React.useState(false);
  const [pinnedId, setPinnedId] = React.useState<string | null>(null);

  const togglePanel = React.useCallback((next: "people" | "chat" | "notes" | "integrity") => {
    setPanel((current) => (current === next ? null : next));
  }, []);

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
  const shareTile = mediaTiles.find((tile) => tile.screenTrack !== undefined);
  const presenterName =
    participants.find((participant) => participant.user_id === shareTile?.id)?.name ??
    shareTile?.name ??
    "";
  const speakingSet = React.useMemo(() => new Set(speakingIds), [speakingIds]);

  // A pinned participant leaves → the pin dies with them (render-phase
  // derivation, no effect needed).
  const pinnedParticipant = pinnedId
    ? (participants.find((participant) => participant.user_id === pinnedId) ?? null)
    : null;
  const pinnedOnStage = shareTile ? null : pinnedParticipant;

  // Stage precedence: active screen share > pinned participant > yourself.
  // While someone else holds the stage, your camera moves into the strip.
  const stripCandidates: WsParticipant[] =
    shareTile || pinnedOnStage ? [...(self ? [self] : []), ...others] : others;
  const stripParticipants = pinnedOnStage
    ? stripCandidates.filter((participant) => participant.user_id !== pinnedOnStage.user_id)
    : stripCandidates;

  // Keyboard shortcuts promised on the control labels (M/V/S/C/R); never
  // fire while the user is typing into a field.
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      ) {
        return;
      }
      switch (event.key.toLowerCase()) {
        case "m":
          onToggleMic();
          break;
        case "v":
          onToggleCamera();
          break;
        case "s":
          if (!canScreenShare) {
            toast.add({
              type: "error",
              title: "Screen sharing is turned off",
              description: "The host turned off screen sharing for this meet.",
            });
            return;
          }
          onToggleScreenShare?.();
          break;
        case "c":
          togglePanel("chat");
          break;
        case "r":
          onToggleHand();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canScreenShare, onToggleCamera, onToggleHand, onToggleMic, onToggleScreenShare, togglePanel]);

  const meetingCode = meeting?.code ?? code;
  const inviteUrl = `${typeof window === "undefined" ? "" : window.location.origin}/room/${meetingCode}`;
  const copyText = async (text: string, doneTitle: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.add({ type: "success", title: doneTitle });
    } catch {
      toast.add({ type: "error", title: "Couldn't copy to the clipboard" });
    }
  };

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
        onShowDetails={() => setDetailsOpen(true)}
        onOpenPeople={() => togglePanel("people")}
      />

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <main className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="min-h-0 flex-1">
            {shareTile?.screenTrack ? (
              <div className="bg-muted relative flex h-full w-full items-center justify-center overflow-hidden rounded-xl border shadow-sm">
                <TrackVideo track={shareTile.screenTrack} />
                <span className="bg-background/80 text-foreground absolute top-2 left-2 rounded-md px-2 py-1 text-xs font-medium backdrop-blur-sm">
                  {shareTile.id === selfUserId
                    ? "You are presenting"
                    : `${presenterName} is presenting`}
                </span>
              </div>
            ) : pinnedOnStage ? (
              <ParticipantTile
                name={pinnedOnStage.name}
                isMuted={!pinnedOnStage.mic_on}
                isCameraOff={!pinnedOnStage.camera_on}
                isScreenSharing={pinnedOnStage.screen_share_on}
                isHandRaised={pinnedOnStage.hand_raised}
                isHost={pinnedOnStage.is_host}
                isPinned
                onPin={() => setPinnedId(null)}
                isSpeaking={speakingSet.has(pinnedOnStage.user_id)}
                connection="excellent"
                media={videoFor(mediaTiles.find((tile) => tile.id === pinnedOnStage.user_id))}
                className="h-full w-full"
              />
            ) : (
              <ParticipantTile
                name={`${self?.name ?? displayName} (You)`}
                isMuted={!micOn}
                isCameraOff={!cameraOn}
                isScreenSharing={isScreenSharing}
                isHandRaised={isHandRaised}
                isHost={self?.is_host ?? true}
                isSpeaking={selfUserId !== null && speakingSet.has(selfUserId)}
                connection="excellent"
                media={videoFor(localTile)}
                className="h-full w-full"
              />
            )}
          </div>

          {stripParticipants.length > 0 ? (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {stripParticipants.map((participant) => (
                <ParticipantTile
                  key={participant.user_id}
                  name={
                    participant.user_id === selfUserId
                      ? `${participant.name} (You)`
                      : participant.name
                  }
                  isMuted={!participant.mic_on}
                  isCameraOff={!participant.camera_on}
                  isScreenSharing={
                    participant.user_id === selfUserId
                      ? isScreenSharing
                      : participant.screen_share_on
                  }
                  isHandRaised={participant.hand_raised}
                  isHost={participant.is_host}
                  isPinned={pinnedId === participant.user_id}
                  onPin={
                    participant.user_id === selfUserId
                      ? undefined
                      : () => setPinnedId(participant.user_id)
                  }
                  isSpeaking={speakingSet.has(participant.user_id)}
                  connection="excellent"
                  media={videoFor(mediaTiles.find((tile) => tile.id === participant.user_id))}
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

          <footer className="relative flex flex-col items-center gap-2 pb-1">
            <FloatingReactions reactions={reactions} />
            {/* Phase 16 — student: always-visible proctoring indicator. */}
            {isExam && !isHost ? (
              <StudentProctorChip
                status={proctorStatus}
                message={proctorMessage}
                onRetry={onRetryProctoring ?? (() => {})}
              />
            ) : null}
            {/* Phase 16 — host: quick-open integrity panel. */}
            {isExam && isHost ? (
              <Button
                variant={panel === "integrity" ? "secondary" : "outline"}
                size="sm"
                onClick={() => togglePanel("integrity")}
                className="bg-background/80 absolute top-0 right-0 backdrop-blur-sm"
              >
                <ShieldAlertIcon className="text-warning size-4" aria-hidden="true" />
                Integrity ({proctorFlags.length})
              </Button>
            ) : null}
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
                isScreenSharing,
                isHandRaised,
              }}
              isReactionsOpen={isReactionsOpen}
              onToggleMic={onToggleMic}
              onToggleCamera={onToggleCamera}
              onToggleScreenShare={() => {
                if (!canScreenShare) {
                  toast.add({
                    type: "error",
                    title: "Screen sharing is turned off",
                    description: "The host turned off screen sharing for this meet.",
                  });
                  return;
                }
                onToggleScreenShare?.();
              }}
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
              canEndMeeting={isSelfHost}
              onEndMeeting={() => setEndOpen(true)}
              onLeave={onLeave}
            />
          </footer>
        </main>

        {panel === "people" ? (
          <div className="w-96 max-w-full shrink-0">
            <PeoplePanel
              participants={panelParticipants}
              canManage={isSelfHost}
              pendingJoins={pendingJoins}
              onApproveJoin={onApproveJoin}
              onRejectJoin={onRejectJoin}
              onMute={(id) => onHostAction("mute_participant", { target_id: id })}
              onRemove={(id) => onHostAction("remove", { target_id: id })}
              onAddPeople={() => {
                // The invite is the link (D25): native share sheet on mobile,
                // clipboard fallback on desktop.
                void shareOrCopyLink(
                  inviteUrl,
                  meeting?.title ? `${meeting.title} — Procto` : "Join my meet on Procto",
                ).then((outcome) => {
                  if (outcome === "copied") {
                    toast.add({
                      type: "success",
                      title: "Invite link copied",
                      description: "Paste it in any chat — the code travels with the link.",
                    });
                  } else if (outcome === "failed") {
                    toast.add({
                      type: "error",
                      title: "Couldn't share the link",
                      description: inviteUrl,
                    });
                  }
                });
              }}
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

        {panel === "integrity" && isExam && isHost ? (
          <div className="w-96 max-w-full shrink-0">
            <IntegrityPanel
              flags={proctorFlags}
              meetingCode={meetingCode}
              onClose={() => setPanel(null)}
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

      <Dialog open={isDetailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{meeting?.title || "Meeting details"}</DialogTitle>
            <DialogDescription>Share the code or link so others can join.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="bg-muted flex items-center justify-between gap-3 rounded-md px-3 py-2">
              <span className="font-mono text-sm">{meetingCode}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void copyText(meetingCode, "Invite code copied")}
              >
                Copy code
              </Button>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground truncate text-xs">{inviteUrl}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void copyText(inviteUrl, "Invite link copied")}
              >
                Copy link
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={isEndOpen} onOpenChange={setEndOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>End the meet for everyone?</AlertDialogTitle>
            <AlertDialogDescription>
              Everyone will be disconnected and the meeting closed for good.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive-solid"
              onClick={() => {
                setEndOpen(false);
                onHostAction("end");
              }}
            >
              End meeting
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
