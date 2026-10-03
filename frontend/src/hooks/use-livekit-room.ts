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
] as const;

function readTiles(room: Room): MediaTile[] {
  const participants = [room.localParticipant, ...room.remoteParticipants.values()];
  return participants.map((participant) => {
    const camera = participant.getTrackPublication(Track.Source.Camera);
    const microphone = participant.getTrackPublication(Track.Source.Microphone);
    return {
      id: participant.identity,
      name: participant.name || participant.identity,
      isLocal: participant === room.localParticipant,
      cameraTrack: camera && !camera.isMuted ? camera.track : undefined,
      audioTrack: microphone && !microphone.isMuted ? microphone.track : undefined,
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
export function useLiveKitRoom(code: string, micOn: boolean, cameraOn: boolean) {
  const [status, setStatus] = React.useState<MediaStatus>("idle");
  const [tiles, setTiles] = React.useState<MediaTile[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const roomRef = React.useRef<Room | null>(null);
  const desiredRef = React.useRef({ micOn, cameraOn });

  React.useEffect(() => {
    desiredRef.current = { micOn, cameraOn };
  }, [micOn, cameraOn]);

  React.useEffect(() => {
    let cancelled = false;
    let room: Room | null = null;
    const detach: Array<[RoomEvent, () => void]> = [];

    const refresh = () => {
      if (room) setTiles(readTiles(room));
    };
    const onState = () => {
      if (!room || cancelled) return;
      if (room.state === ConnectionState.Reconnecting) setStatus("reconnecting");
      else if (room.state === ConnectionState.Connected) setStatus("connected");
      else if (room.state === ConnectionState.Disconnected) setStatus("failed");
    };

    (async () => {
      try {
        setStatus("connecting");
        setError(null);
        const credentials = await meetingsApi.getToken(code);
        if (cancelled) return;

        room = new Room({ adaptiveStream: true, dynacast: true });
        for (const event of ROOM_EVENTS) {
          room.on(event, refresh);
          detach.push([event, refresh]);
        }
        room.on(RoomEvent.ConnectionStateChanged, onState);
        detach.push([RoomEvent.ConnectionStateChanged, onState]);

        await room.connect(credentials.url, credentials.token);
        if (cancelled) {
          room.disconnect();
          return;
        }
        roomRef.current = room;
        await Promise.allSettled([
          room.localParticipant.setMicrophoneEnabled(desiredRef.current.micOn),
          room.localParticipant.setCameraEnabled(desiredRef.current.cameraOn),
        ]);
        if (cancelled) return;
        setStatus("connected");
        setTiles(readTiles(room));
      } catch (err) {
        if (cancelled) return;
        setStatus("failed");
        setError(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => {
      cancelled = true;
      roomRef.current = null;
      if (room) {
        for (const [event, handler] of detach) room.off(event, handler);
        room.disconnect();
      }
      setTiles([]);
    };
  }, [code]);

  // Push mic/camera toggles into LiveKit once connected; before that the
  // post-connect apply above reads the latest desired flags.
  React.useEffect(() => {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) return;
    void room.localParticipant.setMicrophoneEnabled(micOn);
    void room.localParticipant.setCameraEnabled(cameraOn);
  }, [micOn, cameraOn]);

  return { status, tiles, error };
}
