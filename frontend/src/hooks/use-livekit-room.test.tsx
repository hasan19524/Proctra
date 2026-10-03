// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from "@testing-library/react";
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
    getTrackPublication = vi.fn(() => undefined);
  }

  class FakeRoom {
    static instances: FakeRoom[] = [];
    state = "disconnected";
    localParticipant = new FakeLocalParticipant();
    remoteParticipants = new Map<string, unknown>();
    connect = vi.fn(async () => {
      this.state = "connected";
    });
    disconnect = vi.fn(() => undefined);
    on = vi.fn(() => undefined);
    off = vi.fn(() => undefined);

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
    expect(meetingsApi.getToken).toHaveBeenCalledWith("ktq-vxm-pnz");

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

  it("reports failure when the token cannot be minted", async () => {
    const { meetingsApi } = await import("@/lib/api");
    vi.mocked(meetingsApi.getToken).mockRejectedValueOnce(new Error("403 forbidden"));

    const { result } = renderHook(() => useLiveKitRoom("ktq-vxm-pnz", true, true));

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.error).toContain("403");
  });
});
