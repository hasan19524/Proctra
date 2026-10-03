// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMeetingWs } from "@/hooks/use-meeting-ws";

vi.mock("@/lib/api", () => ({
  getAccessToken: vi.fn(() => "token-1"),
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  serverOpen() {
    this.readyState = 1;
    this.onopen?.();
  }

  serverMessage(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  static last(): MockWebSocket {
    const instance = MockWebSocket.instances.at(-1);
    if (!instance) throw new Error("no WebSocket instances");
    return instance;
  }
}

function chatMessage(id: string, seq: number, body: string) {
  return {
    id,
    sender_id: "u1",
    sender_name: "Host Person",
    body,
    client_id: null,
    seq,
    created_at: "2026-10-03T12:00:00+00:00",
    deleted_at: null,
  };
}

describe("useMeetingWs chat", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("merges snapshot tail and chat.message frames, deduplicated by id", async () => {
    const { result } = renderHook(() => useMeetingWs("abc-def-ghi"));
    await act(async () => {
      MockWebSocket.last().serverOpen();
    });
    expect(result.current.status).toBe("open");

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "sync.state",
        id: "s1",
        ts: "2026-10-03T12:00:00.000Z",
        payload: {
          self: { user_id: "u1" },
          participants: [],
          messages: [chatMessage("m1", 1, "hello from the tail")],
        },
      });
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.selfUserId).toBe("u1");

    // Replay overlap: same id again is ignored (at-least-once delivery).
    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "chat.message",
        id: "s2",
        ts: "2026-10-03T12:00:01.000Z",
        seq: 2,
        payload: chatMessage("m1", 1, "hello from the tail"),
      });
    });
    expect(result.current.messages).toHaveLength(1);

    // A genuinely new message lands, ordered by seq.
    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "chat.message",
        id: "s3",
        ts: "2026-10-03T12:00:02.000Z",
        seq: 3,
        payload: chatMessage("m2", 2, "second message"),
      });
    });
    expect(result.current.messages.map((message) => message.id)).toEqual(["m1", "m2"]);
  });

  it("sendChat trims the body, attaches a client id, and queues on the socket", async () => {
    const { result } = renderHook(() => useMeetingWs("abc-def-ghi"));
    await act(async () => {
      MockWebSocket.last().serverOpen();
    });

    let sentId: string | null = null;
    act(() => {
      sentId = result.current.sendChat("  hello procto  ");
    });
    expect(sentId).toBeTruthy();

    const ws = MockWebSocket.last();
    const frames = ws.sent.map((raw) => JSON.parse(raw) as { type: string; payload: unknown });
    const chatFrame = frames.find((frame) => frame.type === "chat.send");
    expect(chatFrame).toBeDefined();
    const payload = chatFrame?.payload as { body: string; client_id: string };
    expect(payload.body).toBe("hello procto");
    expect(payload.client_id).toBeTruthy();

    act(() => {
      expect(result.current.sendChat("   ")).toBeNull();
    });
  });
});

describe("useMeetingWs host controls", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function openWithSelf() {
    const { result } = renderHook(() => useMeetingWs("abc-def-ghi"));
    await act(async () => {
      MockWebSocket.last().serverOpen();
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "sync.state",
        id: "s1",
        ts: "2026-10-03T12:00:00.000Z",
        payload: {
          self: { user_id: "u1" },
          participants: [{ user_id: "u1", name: "Host Person", is_host: true }],
          meeting: {
            status: "active",
            is_locked: false,
            allow_chat: true,
            allow_reactions: true,
            allow_screen_share: true,
          },
        },
      });
    });
    return result;
  }

  it("tracks meeting meta updates from lock, permission, and ended frames", async () => {
    const result = await openWithSelf();
    expect(result.current.meeting?.is_locked).toBe(false);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "meeting.locked",
        id: "s2",
        ts: "2026-10-03T12:00:01.000Z",
        payload: { is_locked: true },
      });
    });
    expect(result.current.meeting?.is_locked).toBe(true);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "permission.changed",
        id: "s3",
        ts: "2026-10-03T12:00:02.000Z",
        payload: { allow_chat: false },
      });
    });
    expect(result.current.meeting?.allow_chat).toBe(false);
    expect(result.current.meeting?.allow_reactions).toBe(true);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "meeting.ended",
        id: "s4",
        ts: "2026-10-03T12:00:03.000Z",
        payload: {},
      });
    });
    expect(result.current.meeting?.status).toBe("ended");
  });

  it("sendHostAction frames host.action with the action name and payload", async () => {
    const result = await openWithSelf();

    let frameId: string | null = null;
    act(() => {
      frameId = result.current.sendHostAction("mute_participant", { target_id: "u2" });
    });
    expect(frameId).toBeTruthy();

    const frames = MockWebSocket.last().sent.map(
      (raw) => JSON.parse(raw) as { type: string; payload: Record<string, unknown> },
    );
    const action = frames.find((frame) => frame.type === "host.action");
    expect(action).toBeDefined();
    expect(action?.payload.action).toBe("mute_participant");
    expect(action?.payload.target_id).toBe("u2");
  });

  it("marks removal and counts self-mutes for the right user only", async () => {
    const result = await openWithSelf();
    expect(result.current.isRemoved).toBe(false);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "participant.removed",
        id: "s2",
        ts: "2026-10-03T12:00:01.000Z",
        payload: { user_id: "someone-else" },
      });
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "participant.muted",
        id: "s3",
        ts: "2026-10-03T12:00:02.000Z",
        payload: { user_id: "someone-else", by_user_id: "u1" },
      });
    });
    expect(result.current.isRemoved).toBe(false);
    expect(result.current.selfMuteNonce).toBe(0);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "participant.muted",
        id: "s4",
        ts: "2026-10-03T12:00:03.000Z",
        payload: { user_id: "u1", by_user_id: "u1" },
      });
    });
    expect(result.current.selfMuteNonce).toBe(1);
    expect(result.current.isRemoved).toBe(false);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "participant.removed",
        id: "s5",
        ts: "2026-10-03T12:00:04.000Z",
        payload: { user_id: "u1" },
      });
    });
    expect(result.current.isRemoved).toBe(true);
  });
});

describe("useMeetingWs notes", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function note(id: string, visibility: string, text: string) {
    return {
      id,
      meeting_id: "m1",
      visibility,
      content: { text },
      updated_by: "u1",
      updated_by_name: "Host Person",
      updated_at: "2026-10-03T12:00:00+00:00",
    };
  }

  it("seeds notes from sync.state and upserts note.updated by id", async () => {
    const { result } = renderHook(() => useMeetingWs("abc-def-ghi"));
    await act(async () => {
      MockWebSocket.last().serverOpen();
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "sync.state",
        id: "s1",
        ts: "2026-10-03T12:00:00.000Z",
        payload: { self: { user_id: "u1" }, notes: [note("n1", "all", "agenda v1")] },
      });
    });
    expect(result.current.notes).toHaveLength(1);

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "note.updated",
        id: "s2",
        ts: "2026-10-03T12:00:01.000Z",
        payload: note("n1", "all", "agenda v2"),
      });
    });
    expect(result.current.notes).toHaveLength(1);
    expect(result.current.notes[0].content.text).toBe("agenda v2");

    await act(async () => {
      MockWebSocket.last().serverMessage({
        v: 1,
        type: "note.updated",
        id: "s3",
        ts: "2026-10-03T12:00:02.000Z",
        payload: note("n2", "host_only", "private"),
      });
    });
    expect(result.current.notes.map((n) => n.visibility)).toEqual(["all", "host_only"]);
  });

  it("sendNoteSave frames note.save with visibility and text content", async () => {
    const { result } = renderHook(() => useMeetingWs("abc-def-ghi"));
    await act(async () => {
      MockWebSocket.last().serverOpen();
    });

    let frameId: string | null = null;
    act(() => {
      frameId = result.current.sendNoteSave("all", { text: "hello notes" });
    });
    expect(frameId).toBeTruthy();

    const frames = MockWebSocket.last().sent.map(
      (raw) => JSON.parse(raw) as { type: string; payload: Record<string, unknown> },
    );
    const save = frames.find((frame) => frame.type === "note.save");
    expect(save).toBeDefined();
    expect(save?.payload.visibility).toBe("all");
    expect(save?.payload.content).toEqual({ text: "hello notes" });
  });
});
