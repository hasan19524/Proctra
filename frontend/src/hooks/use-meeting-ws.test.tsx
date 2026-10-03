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
