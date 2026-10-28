"use client";

import * as React from "react";
import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";

import { meetingsApi } from "@/lib/api";

export type MediaStatus = "idle" | "connecting" | "connected" | "reconnecting" | "failed";

/** One LiveKit participant's media view, matched to WS roster by identity (= user id). */
export interface MediaTile {
  id: string;
  name: string;
  isLocal: boolean;
  cameraTrack?: Track;
  audioTrack?: Track;
  screenTrack?: Track;
}

const ROOM_EVENTS = [
  RoomEvent.Connected,
  RoomEvent.Reconnected,
  RoomEvent.Reconnecting,
  RoomEvent.Disconnected,
  RoomEvent.ConnectionStateChanged,
  RoomEvent.ParticipantConnected,
  RoomEvent.ParticipantDisconnected,
  RoomEvent.ParticipantNameChanged,
  RoomEvent.TrackPublished,
  RoomEvent.TrackUnpublished,
  RoomEvent.TrackSubscribed,
  RoomEvent.TrackUnsubscribed,
  RoomEvent.TrackMuted,
  RoomEvent.TrackUnmuted,
  RoomEvent.TrackSubscriptionStatusChanged,
  RoomEvent.LocalTrackPublished,
  RoomEvent.LocalTrackUnpublished,
  RoomEvent.LocalTrackSubscribed,
  RoomEvent.ActiveSpeakersChanged,
] as const;

function readTiles(room: Room): MediaTile[] {
  const participants = [room.localParticipant, ...room.remoteParticipants.values()];
  return participants.map((participant) => {
    const camera = participant.getTrackPublication(Track.Source.Camera);
    const microphone = participant.getTrackPublication(Track.Source.Microphone);
    const screen = participant.getTrackPublication(Track.Source.ScreenShare);
    return {
      id: participant.identity,
      name: participant.name || participant.identity,
      isLocal: participant === room.localParticipant,
      cameraTrack: camera && !camera.isMuted ? camera.track : undefined,
      audioTrack: microphone && !microphone.isMuted ? microphone.track : undefined,
      screenTrack: screen && !screen.isMuted ? screen.track : undefined,
    };
  });
}

/**
 * Connect one LiveKit room for the call's media (ARCHITECTURE.md §8).
 *
 * Roster/presence stays on the app WebSocket; this hook only owns the SFU:
 * fetch a short-lived token, connect, keep mic/camera publications in sync
 * with the caller's chosen flags, and project participants as renderable
 * tiles (identity = user id so tiles match roster entries).
 */
export function useLiveKitRoom(
  code: string | null,
  micOn: boolean,
  cameraOn: boolean,
  password?: string,
) {
  const [status, setStatus] = React.useState<MediaStatus>("idle");
  const [tiles, setTiles] = React.useState<MediaTile[]>([]);
  const [speakingIds, setSpeakingIds] = React.useState<string[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const roomRef = React.useRef<Room | null>(null);
  const desiredRef = React.useRef({ micOn, cameraOn });

  React.useEffect(() => {
    desiredRef.current = { micOn, cameraOn };
  }, [micOn, cameraOn]);

  React.useEffect(() => {
    let cancelled = false;
    let room: Room | null = null;
    // Set after the first successful handshake: from then on an unexpected
    // Disconnected is a real session loss (LiveKit gave up, e.g. an expired
    // token) rather than a failed initial connect.
    let hadSession = false;
    let recovered = false;
    const detach: Array<[RoomEvent, () => void, Room]> = [];

    const refresh = () => {
      if (!room) return;
      setTiles(readTiles(room));
      setSpeakingIds(room.activeSpeakers.map((participant) => participant.identity));
    };

    const onState = () => {
      if (!room || cancelled) return;
      if (room.state === ConnectionState.Reconnecting) {
        setStatus("reconnecting");
        return;
      }
      if (room.state === ConnectionState.Connected) {
        setStatus("connected");
        return;
      }
      if (room.state !== ConnectionState.Disconnected) return;
      // Before a session exists, the handshake loop reports failure; do not
      // set "failed" from a late Disconnected event fired by a room being torn
      // down or rejected.
      if (!hadSession) return;
      // ...and we allow exactly one re-mint + reconnect (REALTIME.md:126)...
      if (!recovered) {
        recovered = true;
        void recover();
        return;
      }
      setStatus("failed");
    };

    const detachRoom = (target: Room) => {
      for (const [event, handler, owner] of detach) {
        if (owner === target) target.off(event, handler);
      }
    };

    const buildRoom = (): Room => {
      const next = new Room({ adaptiveStream: true, dynacast: true });
      for (const event of ROOM_EVENTS) {
        next.on(event, refresh);
        detach.push([event, refresh, next]);
      }
      next.on(RoomEvent.ConnectionStateChanged, onState);
      detach.push([RoomEvent.ConnectionStateChanged, onState, next]);
      return next;
    };

    /** Handshake against a freshly minted token; false when superseded. */
    const handoff = async (target: Room): Promise<boolean> => {
      const credentials = await meetingsApi.getToken(code!, password);
      if (cancelled) return false;
      await target.connect(credentials.url, credentials.token);
      if (cancelled) {
        target.disconnect();
        return false;
      }
      roomRef.current = target;
      await Promise.allSettled([
        target.localParticipant.setMicrophoneEnabled(desiredRef.current.micOn),
        target.localParticipant.setCameraEnabled(desiredRef.current.cameraOn),
      ]);
      if (cancelled) return false;
      setStatus("connected");
      refresh();
      return true;
    };

    /** One bounded recovery: tear the dead room down, re-mint, reconnect. */
    const recover = async () => {
      const previous = room;
      if (previous) {
        detachRoom(previous);
        previous.disconnect();
      }
      try {
        room = buildRoom();
        setStatus("reconnecting");
        const connected = await handoff(room);
        if (connected && !cancelled) setError(null);
      } catch (err) {
        if (cancelled) return;
        room = null;
        roomRef.current = null;
        setStatus("failed");
        setError(err instanceof Error ? err.message : String(err));
      }
    };

    (async () => {
      setStatus("connecting");
      setError(null);
      // Initial handshake retries once with a fresh token (expired mint or a
      // transient network failure); each attempt gets its own Room.
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 2 && !cancelled; attempt += 1) {
        try {
          room = buildRoom();
          const connected = await handoff(room);
          if (connected) {
            hadSession = true;
            return;
          }
          return; // superseded by unmount
        } catch (err) {
          lastError = err;
          if (cancelled) return;
          if (room) {
            detachRoom(room);
            room.disconnect();
            room = null;
          }
        }
      }
      if (cancelled) return;
      setStatus("failed");
      setError(lastError instanceof Error ? lastError.message : String(lastError));
    })();

    return () => {
      cancelled = true;
      roomRef.current = null;
      for (const [event, handler, owner] of detach) owner.off(event, handler);
      if (room) room.disconnect();
      setTiles([]);
      setSpeakingIds([]);
    };
  }, [code, password]);

  // Push mic/camera toggles into LiveKit once connected; before that the
  // post-connect apply above reads the latest desired flags.
  React.useEffect(() => {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) return;
    void room.localParticipant.setMicrophoneEnabled(micOn);
    void room.localParticipant.setCameraEnabled(cameraOn);
  }, [micOn, cameraOn]);

  // Screen share is driven by the local publication itself (the browser's
  // picker can be cancelled, and ESC stops sharing outside our UI), so the
  // "am I sharing" answer is derived from tiles rather than mirrored state.
  const screenShareOn = tiles.some((tile) => tile.isLocal && tile.screenTrack !== undefined);

  /** Start/stop the local screen-share publication; resolves to the new
   * on/off state, or null when the room is not ready or the user declined. */
  const toggleScreenShare = React.useCallback(async (): Promise<boolean | null> => {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) return null;
    const current = room.localParticipant.getTrackPublication(Track.Source.ScreenShare);
    const next = !(current && !current.isMuted);
    try {
      await room.localParticipant.setScreenShareEnabled(next);
      setTiles(readTiles(room));
      return next;
    } catch {
      return null;
    }
  }, []);

  return { status, tiles, speakingIds, error, screenShareOn, toggleScreenShare };
}
