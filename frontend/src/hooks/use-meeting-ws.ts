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

interface SyncStatePayload {
  self?: { user_id: string };
  participants?: WsParticipant[];
  messages?: WsChatMessage[];
}

interface PresenceStatePayload {
  participants?: WsParticipant[];
}

export interface ParticipantFlags {
  mic_on?: boolean;
  camera_on?: boolean;
  hand_raised?: boolean;
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
export function useMeetingWs(code: string | null) {
  const [status, setStatus] = React.useState<WsStatus>("closed");
  const [participants, setParticipants] = React.useState<WsParticipant[]>([]);
  const [selfUserId, setSelfUserId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<WsChatMessage[]>([]);
  const socketRef = React.useRef<MeetingSocket | null>(null);

  React.useEffect(() => {
    if (!code) return;

    const socket = new MeetingSocket(code, getAccessToken);
    socketRef.current = socket;

    const unsubscribes = [
      socket.onStatus(setStatus),
      socket.on<SyncStatePayload>("sync.state", (payload) => {
        if (payload?.self?.user_id) setSelfUserId(payload.self.user_id);
        if (Array.isArray(payload?.participants)) setParticipants(payload.participants);
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

  return { status, participants, selfUserId, messages, updateFlags, sendChat };
}
