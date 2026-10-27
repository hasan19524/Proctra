"use client";

import * as React from "react";

import { getAccessToken } from "@/lib/api";
import { MeetingSocket, newId, type WsStatus } from "@/lib/ws";

export interface WsParticipant {
  user_id: string;
  name: string;
  is_host: boolean;
  mic_on: boolean;
  camera_on: boolean;
  hand_raised: boolean;
  screen_share_on: boolean;
  joined_at?: string;
}

export interface WsChatMessage {
  id: string;
  sender_id: string;
  sender_name: string;
  body: string;
  client_id: string | null;
  seq: number;
  created_at: string;
}

export interface MeetingMeta {
  code: string;
  title: string;
  status: string;
  is_locked: boolean;
  allow_chat: boolean;
  allow_reactions: boolean;
  allow_screen_share: boolean;
}

export type NoteVisibility = "all" | "host_only";

/** One transient reaction (never persisted; expires client-side). */
export interface WsReaction {
  id: number;
  user_id: string;
  name: string;
  label: string;
  at: number;
}

export interface WsNote {
  id: string;
  meeting_id: string;
  visibility: NoteVisibility;
  content: { text?: string };
  updated_by: string | null;
  updated_by_name: string | null;
  updated_at: string;
}

interface SyncStatePayload {
  self?: { user_id: string };
  participants?: WsParticipant[];
  messages?: WsChatMessage[];
  meeting?: MeetingMeta;
  notes?: WsNote[];
}

interface PresenceStatePayload {
  participants?: WsParticipant[];
}

interface MeetingLockedPayload {
  is_locked: boolean;
}

interface PermissionChangedPayload {
  allow_chat?: boolean;
  allow_reactions?: boolean;
  allow_screen_share?: boolean;
}

interface ParticipantEventPayload {
  user_id: string;
  by_user_id?: string;
}

interface ReactionPayload {
  user_id?: string;
  name?: string;
  label?: string;
}

const REACTION_TTL_MS = 5_000;
const REACTION_MAX_KEPT = 20;
let reactionSeq = 0;

export interface ParticipantFlags {
  mic_on?: boolean;
  camera_on?: boolean;
  hand_raised?: boolean;
  screen_share_on?: boolean;
}

/**
 * Merge by id and order by seq: chat delivery is at-least-once, so replay and
 * snapshot tails can overlap (REALTIME.md §3). Returns the same reference when
 * nothing new arrived.
 */
function upsertMessages(existing: WsChatMessage[], incoming: WsChatMessage[]): WsChatMessage[] {
  const byId = new Map(existing.map((message) => [message.id, message]));
  let changed = false;
  for (const message of incoming) {
    if (!byId.has(message.id)) {
      byId.set(message.id, message);
      changed = true;
    }
  }
  if (!changed) return existing;
  return [...byId.values()].sort((a, b) => a.seq - b.seq);
}

/**
 * Owns the meeting WebSocket for one room: connection status, the live
 * participant roster (from `sync.state` / `presence.state`), and the chat log
 * (`sync.state` tail + `chat.message` frames). The socket is created once per
 * `code` and torn down on unmount.
 */
export function useMeetingWs(code: string | null, password?: string) {
  const [status, setStatus] = React.useState<WsStatus>("closed");
  const [participants, setParticipants] = React.useState<WsParticipant[]>([]);
  const [selfUserId, setSelfUserId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<WsChatMessage[]>([]);
  const [meeting, setMeeting] = React.useState<MeetingMeta | null>(null);
  const [notes, setNotes] = React.useState<WsNote[]>([]);
  const [reactions, setReactions] = React.useState<WsReaction[]>([]);
  const [isRemoved, setIsRemoved] = React.useState(false);
  const [selfMuteNonce, setSelfMuteNonce] = React.useState(0);
  const [isWaiting, setIsWaiting] = React.useState(false);
  const [isRejected, setIsRejected] = React.useState(false);
  const [pendingJoins, setPendingJoins] = React.useState<Array<{ user_id: string; name: string }>>([]);
  const socketRef = React.useRef<MeetingSocket | null>(null);
  // The self id arrives with sync.state, but frames can reference it first;
  // a ref lets early events match without re-subscribing the socket.
  const selfUserIdRef = React.useRef<string | null>(null);
  const passwordRef = React.useRef<string | undefined>(password);

  React.useEffect(() => {
    passwordRef.current = password;
  }, [password]);

  React.useEffect(() => {
    selfUserIdRef.current = selfUserId;
  }, [selfUserId]);

  React.useEffect(() => {
    if (!code) return;

    const socket = new MeetingSocket(code, getAccessToken, () => passwordRef.current);
    socketRef.current = socket;

    const unsubscribes = [
      socket.onStatus(setStatus),
      socket.on<SyncStatePayload>("sync.state", (payload) => {
        setIsWaiting(false);
        if (payload?.self?.user_id) setSelfUserId(payload.self.user_id);
        if (Array.isArray(payload?.participants)) setParticipants(payload.participants);
        if (payload?.meeting) setMeeting(payload.meeting);
        if (Array.isArray(payload?.notes)) setNotes(payload.notes);
        if (Array.isArray(payload?.messages) && payload.messages.length > 0) {
          setMessages((current) => upsertMessages(current, payload.messages ?? []));
        }
      }),
      socket.on<PresenceStatePayload>("presence.state", (payload) => {
        if (Array.isArray(payload?.participants)) setParticipants(payload.participants);
      }),
      socket.on<WsChatMessage>("chat.message", (payload) => {
        if (payload && typeof payload.id === "string") {
          setMessages((current) => upsertMessages(current, [payload]));
        }
      }),
      socket.on("waiting.state", (payload: unknown) => {
        const p = payload as { approved?: boolean } | undefined;
        if (p?.approved) {
          setIsWaiting(false);
          socket.send("sync", {});
        } else {
          setIsWaiting(true);
        }
      }),
      socket.on("waiting.approved", (payload: unknown) => {
        const p = payload as { user_id?: string } | undefined;
        if (p?.user_id && p.user_id === selfUserIdRef.current) {
          setIsWaiting(false);
          socket.send("sync", {});
        }
        if (p?.user_id) {
          setPendingJoins((current) => current.filter((entry) => entry.user_id !== p.user_id));
        }
      }),
      socket.on("waiting.rejected", (payload: unknown) => {
        const p = payload as { user_id?: string } | undefined;
        if (p?.user_id && p.user_id === selfUserIdRef.current) {
          setIsRejected(true);
          setIsWaiting(false);
        }
        if (p?.user_id) {
          setPendingJoins((current) => current.filter((entry) => entry.user_id !== p.user_id));
        }
      }),
      socket.on("join.request", (payload: unknown) => {
        const p = payload as { user_id?: string; name?: string } | undefined;
        if (p?.user_id && p.user_id !== selfUserIdRef.current) {
          setPendingJoins((current) => {
            if (current.some((entry) => entry.user_id === p.user_id)) return current;
            return [...current, { user_id: p.user_id!, name: p.name ?? "" }];
          });
        }
      }),
      socket.on<MeetingLockedPayload>("meeting.locked", (payload) => {
        if (payload && typeof payload.is_locked === "boolean") {
          setMeeting((current) =>
            current ? { ...current, is_locked: payload.is_locked } : current,
          );
        }
      }),
      socket.on<PermissionChangedPayload>("permission.changed", (payload) => {
        if (!payload) return;
        setMeeting((current) =>
          current
            ? {
                ...current,
                allow_chat: payload.allow_chat ?? current.allow_chat,
                allow_reactions: payload.allow_reactions ?? current.allow_reactions,
                allow_screen_share: payload.allow_screen_share ?? current.allow_screen_share,
              }
            : current,
        );
      }),
      socket.on("meeting.ended", () => {
        setMeeting((current) => (current ? { ...current, status: "ended" } : current));
        setIsWaiting(false);
      }),
      socket.on<ParticipantEventPayload>("participant.joined", (payload) => {
        if (payload?.user_id) {
          setPendingJoins((current) => current.filter((entry) => entry.user_id !== payload.user_id));
        }
      }),
      socket.on<ParticipantEventPayload>("participant.removed", (payload) => {
        if (payload?.user_id && payload.user_id === selfUserIdRef.current) {
          setIsRemoved(true);
        }
      }),
      socket.on<ParticipantEventPayload>("participant.muted", (payload) => {
        if (payload?.user_id && payload.user_id === selfUserIdRef.current) {
          setSelfMuteNonce((nonce) => nonce + 1);
        }
      }),
      socket.on<WsNote>("note.updated", (payload) => {
        if (!payload || typeof payload.id !== "string") return;
        setNotes((current) => {
          const rest = current.filter((note) => note.id !== payload.id);
          return [...rest, payload].sort((a, b) => a.visibility.localeCompare(b.visibility));
        });
      }),
      socket.on<ReactionPayload>("reaction.received", (payload) => {
        if (!payload?.user_id || !payload.label) return;
        const at = Date.now();
        const incoming: WsReaction = {
          id: reactionSeq++,
          user_id: payload.user_id,
          name: payload.name ?? "",
          label: payload.label,
          at,
        };
        setReactions((current) =>
          [...current, incoming]
            .filter((reaction) => at - reaction.at < REACTION_TTL_MS)
            .slice(-REACTION_MAX_KEPT),
        );
      }),
    ];

    socket.connect();

    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
      socket.close();
      socketRef.current = null;
    };
  }, [code]);

  const updateFlags = React.useCallback((flags: ParticipantFlags) => {
    socketRef.current?.send("presence.update", flags);
  }, []);

  /** Send a host-only action; returns the frame id or null when not connected. */
  const sendHostAction = React.useCallback(
    (action: string, payload: Record<string, unknown> = {}): string | null => {
      return socketRef.current?.send("host.action", { action, ...payload }) ?? null;
    },
    [],
  );

  /** Replace one notes document; returns the frame id or null when offline. */
  const sendNoteSave = React.useCallback(
    (visibility: NoteVisibility, content: { text?: string }): string | null => {
      return socketRef.current?.send("note.save", { visibility, content }) ?? null;
    },
    [],
  );

  /** Fire one transient reaction; returns the frame id or null when offline. */
  const sendReaction = React.useCallback((label: string): string | null => {
    return socketRef.current?.send("reaction.send", { label }) ?? null;
  }, []);

  /**
   * Send a chat message. Returns the idempotency key when queued/sent, or
   * `null` when the socket is closed or the text is blank.
   */
  const sendChat = React.useCallback((body: string): string | null => {
    const trimmed = body.trim();
    if (!trimmed) return null;
    const clientId = newId();
    return socketRef.current?.send("chat.send", { body: trimmed, client_id: clientId }) ?? null;
  }, []);

  return {
    status,
    participants,
    selfUserId,
    messages,
    meeting,
    notes,
    reactions,
    isRemoved,
    selfMuteNonce,
    isWaiting,
    isRejected,
    pendingJoins,
    updateFlags,
    sendChat,
    sendHostAction,
    sendNoteSave,
    sendReaction,
  };
}
