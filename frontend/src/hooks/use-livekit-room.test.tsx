// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveKitRoom } from "@/hooks/use-livekit-room";

vi.mock("@/lib/api", () => ({
  meetingsApi: {
    getToken: vi.fn(async () => ({ url: "ws://localhost:7880", token: "tk-test" })),
  },
}));

const { FakeRoom } = vi.hoisted(() => {
  class FakeLocalParticipant {
    identity = "u1";
    name = "Me";
    setMicrophoneEnabled = vi.fn(async () => undefined);
    setCameraEnabled = vi.fn(async () => undefined);
    setScreenShareEnabled = vi.fn(async () => undefined);
    getTrackPublication = vi.fn(() => undefined);
  }

  class FakeRoom {
    static instances: FakeRoom[] = [];
    state = "disconnected";
    activeSpeakers: Array<{ identity: string }> = [];
    handlers = new Map<string, Array<() => void>>();
    localParticipant = new FakeLocalParticipant();
    remoteParticipants = new Map<string, unknown>();
    connect = vi.fn(async () => {
      this.state = "connected";
    });
    disconnect = vi.fn(() => undefined);
    on = vi.fn((event: string, handler: () => void) => {
      const list = this.handlers.get(event) ?? [];
      list.push(handler);
      this.handlers.set(event, list);
    });
    off = vi.fn((event: string, handler: () => void) => {
      const list = this.handlers.get(event) ?? [];
      const index = list.indexOf(handler);
      if (index >= 0) list.splice(index, 1);
    });

    emit(event: string) {
      for (const handler of this.handlers.get(event) ?? []) handler();
    }

    constructor() {
      FakeRoom.instances.push(this);
    }

    static last(): FakeRoom {
      const room = FakeRoom.instances.at(-1);
      if (!room) throw new Error("no Room instances");
      return room;
    }
  }

  return { FakeRoom };
});

vi.mock("livekit-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("livekit-client")>();
  return {
    ...actual,
    Room: FakeRoom as unknown as typeof actual.Room,
  };
});

describe("useLiveKitRoom", () => {
  beforeEach(() => {
    FakeRoom.instances = [];
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("fetches a token, connects, and applies the initial media flags", async () => {
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, false));
    expect(result.current.status).toBe("connecting");

    await waitFor(() => expect(result.current.status).toBe("connected"));

    const { meetingsApi } = await import("@/lib/api");
    expect(meetingsApi.getToken).toHaveBeenCalledWith("ktq-vxm-pnz", undefined);

    const room = FakeRoom.last();
    expect(room.connect).toHaveBeenCalledWith("ws://localhost:7880", "tk-test");
    expect(room.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
    expect(room.localParticipant.setCameraEnabled).toHaveBeenCalledWith(false);
    expect(result.current.tiles).toHaveLength(1);
    expect(result.current.tiles[0]).toMatchObject({ id: "u1", isLocal: true });
  });

  it("pushes flag changes into LiveKit once connected", async () => {
    const { result, rerender } = renderHook(
      ({ micOn }: { micOn: boolean }) => useLiveKitRoom("ktq-vxm-pnz", micOn, true),
      { initialProps: { micOn: true } },
    );
    await waitFor(() => expect(result.current.status).toBe("connected"));

    rerender({ micOn: false });
    await waitFor(() =>
      expect(FakeRoom.last().localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(false),
    );
  });

  it("disconnects the room on unmount", async () => {
    const { result, unmount } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));

    const room = FakeRoom.last();
    unmount();
    expect(room.disconnect).toHaveBeenCalled();
  });

  it("reports failure when the token can never be minted", async () => {
    const { meetingsApi } = await import("@/lib/api");
    vi.mocked(meetingsApi.getToken)
      .mockRejectedValueOnce(new Error("403 forbidden"))
      .mockRejectedValueOnce(new Error("403 forbidden"));

    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.error).toContain("403");
    expect(vi.mocked(meetingsApi.getToken)).toHaveBeenCalledTimes(2);
  });

  it("toggles the local screen-share publication", async () => {
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));

    const local = FakeRoom.last().localParticipant;
    expect(result.current.screenShareOn).toBe(false);

    // No publication yet: the next toggle starts sharing.
    await act(async () => {
      expect(await result.current.toggleScreenShare()).toBe(true);
    });
    expect(local.setScreenShareEnabled).toHaveBeenCalledWith(true);

    // Publication now exists and is unmuted: the next toggle stops sharing.
    local.getTrackPublication.mockReturnValue({ isMuted: false } as never);
    await act(async () => {
      expect(await result.current.toggleScreenShare()).toBe(false);
    });
    expect(local.setScreenShareEnabled).toHaveBeenLastCalledWith(false);
  });

  it("resolves null when the browser declines the screen-share request", async () => {
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));

    const local = FakeRoom.last().localParticipant;
    local.setScreenShareEnabled.mockRejectedValueOnce(new Error("permission denied"));

    await act(async () => {
      expect(await result.current.toggleScreenShare()).toBeNull();
    });
  });

  it("tracks active speakers as identities", async () => {
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));
    expect(result.current.speakingIds).toEqual([]);

    const { RoomEvent } = await import("livekit-client");
    const room = FakeRoom.last();
    room.activeSpeakers = [{ identity: "u2" }];
    act(() => room.emit(RoomEvent.ActiveSpeakersChanged));

    await waitFor(() => expect(result.current.speakingIds).toEqual(["u2"]));
  });

  it("retries the handshake with a fresh token when the first attempt fails", async () => {
    const { meetingsApi } = await import("@/lib/api");
    vi.mocked(meetingsApi.getToken).mockRejectedValueOnce(new Error("network blip"));

    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));

    await waitFor(() => expect(result.current.status).toBe("connected"));
    expect(vi.mocked(meetingsApi.getToken)).toHaveBeenCalledTimes(2);
    // Each attempt builds its own Room so a poisoned socket is never reused.
    expect(FakeRoom.instances).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it("re-mints a token and recovers once after a mid-session disconnect", async () => {
    const { meetingsApi } = await import("@/lib/api");
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));
    const { RoomEvent } = await import("livekit-client");

    const dead = FakeRoom.last();
    act(() => {
      dead.state = "disconnected";
      dead.emit(RoomEvent.ConnectionStateChanged);
    });
    await waitFor(() => expect(result.current.status).toBe("reconnecting"));

    await waitFor(() => expect(result.current.status).toBe("connected"));
    expect(vi.mocked(meetingsApi.getToken)).toHaveBeenCalledTimes(2);
    expect(FakeRoom.instances).toHaveLength(2);
    expect(FakeRoom.last()).not.toBe(dead);
  });

  it("fails after the single recovery attempt also dies", async () => {
    const { meetingsApi } = await import("@/lib/api");
    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));
    await waitFor(() => expect(result.current.status).toBe("connected"));
    const { RoomEvent } = await import("livekit-client");

    vi.mocked(meetingsApi.getToken).mockRejectedValueOnce(new Error("token mint down"));
    act(() => {
      const dead = FakeRoom.last();
      dead.state = "disconnected";
      dead.emit(RoomEvent.ConnectionStateChanged);
    });

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.error).toContain("token mint down");
    // Exactly one recovery — never a retry storm.
    expect(vi.mocked(meetingsApi.getToken)).toHaveBeenCalledTimes(2);
  });
});
