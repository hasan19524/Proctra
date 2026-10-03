"use client";

import * as React from "react";

import { getAccessToken } from "@/lib/api";
import { MeetingSocket, type WsStatus } from "@/lib/ws";

export interface WsParticipant {
  user_id: string;
  name: string;
  is_host: boolean;
  mic_on: boolean;
  camera_on: boolean;
  hand_raised: boolean;
  joined_at?: string;
}

interface SyncStatePayload {
  self?: { user_id: string };
  participants?: WsParticipant[];
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
 * Owns the meeting WebSocket for one room: connection status, the live
 * participant roster (from `sync.state` / `presence.state`), and a
 * `presence.update` sender. The socket is created once per `code` and torn
 * down on unmount.
 */
export function useMeetingWs(code: string | null) {
  const [status, setStatus] = React.useState<WsStatus>("closed");
  const [participants, setParticipants] = React.useState<WsParticipant[]>([]);
  const [selfUserId, setSelfUserId] = React.useState<string | null>(null);
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
      }),
      socket.on<PresenceStatePayload>("presence.state", (payload) => {
        if (Array.isArray(payload?.participants)) setParticipants(payload.participants);
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

  return { status, participants, selfUserId, updateFlags };
}
