import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MeetingSocket,
  buildFrame,
  meetingWsProtocols,
  meetingWsUrl,
  type WsStatus,
} from "@/lib/ws";

vi.mock("@/lib/api", () => ({
  getAccessToken: vi.fn(() => "token-1"),
  refreshSession: vi.fn(() => Promise.resolve()),
}));

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  url: string;
  protocols: string[];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string, protocols: string[] = []) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close(code = 1000) {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code });
  }

  serverOpen() {
    this.readyState = 1;
    this.onopen?.();
  }

  serverMessage(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  serverClose(code: number) {
    this.readyState = 3;
    this.onclose?.({ code });
  }

  static last(): MockWebSocket {
    const instance = MockWebSocket.instances.at(-1);
    if (!instance) throw new Error("no WebSocket instances");
    return instance;
  }
}

function sentTypes(ws: MockWebSocket): string[] {
  return ws.sent.map((raw) => (JSON.parse(raw) as { type: string }).type);
}

async function flushAsync() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("meetingWsUrl", () => {
  it("builds the backend ws endpoint with no credentials in the URL", () => {
    expect(meetingWsUrl("abc-def-ghi")).toBe("ws://localhost:8001/api/v1/ws/meetings/abc-def-ghi");
  });

  it("honours NEXT_PUBLIC_WS_URL and strips trailing slashes", () => {
    process.env.NEXT_PUBLIC_WS_URL = "ws://api:8001///";
    expect(meetingWsUrl("abc-def-ghi")).toBe("ws://api:8001/api/v1/ws/meetings/abc-def-ghi");
    delete process.env.NEXT_PUBLIC_WS_URL;
  });
});

describe("meetingWsProtocols (H1: credentials never in the URL)", () => {
  function b64url(value: string): string {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  it("encodes the access token as a subprotocol entry", () => {
    expect(meetingWsProtocols("tok en")).toEqual(["procto.v1", `procto.token.${b64url("tok en")}`]);
  });

  it("omits the password entry when no password is supplied", () => {
    const entries = meetingWsProtocols("t");
    expect(entries).toHaveLength(2);
    expect(entries.some((entry) => entry.startsWith("procto.password."))).toBe(false);
  });

  it("appends an encoded password entry when supplied", () => {
    const entries = meetingWsProtocols("t", "s3cret");
    expect(entries).toContain(`procto.password.${b64url("s3cret")}`);
  });
});

describe("buildFrame", () => {
  it("emits a v1 envelope with id and ts", () => {
    const frame = buildFrame("ping", { x: 1 });
    expect(frame.v).toBe(1);
    expect(frame.type).toBe("ping");
    expect(frame.payload).toEqual({ x: 1 });
    expect(frame.id).toBeTruthy();
    expect(Number.isNaN(Date.parse(frame.ts))).toBe(false);
  });
});

describe("MeetingSocket", () => {
  let statuses: WsStatus[];

  beforeEach(() => {
    MockWebSocket.instances = [];
    statuses = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function makeSocket() {
    const socket = new MeetingSocket("abc-def-ghi", () => "token-1");
    socket.onStatus((status) => statuses.push(status));
    return socket;
  }

  it("connects, reports status, and opens with a sync frame", () => {
    const socket = makeSocket();
    socket.connect();

    expect(statuses).toContain("connecting");
    const ws = MockWebSocket.last();
    // H1: the access token must never appear in the URL — it rides the
    // Sec-WebSocket-Protocol header (passed to the WebSocket constructor).
    expect(ws.url).toBe("ws://localhost:8001/api/v1/ws/meetings/abc-def-ghi");
    expect(ws.url).not.toContain("token");
    expect(ws.protocols).toContain("procto.v1");
    expect(ws.protocols).toContain("procto.token.dG9rZW4tMQ"); // b64url("token-1")

    ws.serverOpen();
    expect(socket.getStatus()).toBe("open");
    expect(sentTypes(ws)[0]).toBe("sync");
    socket.close();
    expect(socket.getStatus()).toBe("closed");
  });

  it("sends the meeting password as a subprotocol entry, not in the URL", () => {
    const socket = new MeetingSocket(
      "abc-def-ghi",
      () => "token-1",
      () => "s3cret",
    );
    socket.connect();

    const ws = MockWebSocket.last();
    expect(ws.url).not.toContain("s3cret");
    expect(ws.url).not.toContain("password");
    expect(ws.protocols).toContain("procto.password.czNjcmV0"); // b64url("s3cret")
    socket.close();
  });

  it("queues frames sent while connecting and flushes them on open", () => {
    const socket = makeSocket();
    socket.connect();
    socket.send("presence.update", { mic_on: false });

    const ws = MockWebSocket.last();
    expect(ws.sent).toHaveLength(0);

    ws.serverOpen();
    const frames = ws.sent.map((raw) => JSON.parse(raw) as { type: string });
    expect(frames[0]?.type).toBe("sync");
    expect(frames[1]?.type).toBe("presence.update");
    socket.close();
  });

  it("dispatches server frames to typed handlers and tracks seq", () => {
    const socket = makeSocket();
    socket.connect();
    const ws = MockWebSocket.last();
    ws.serverOpen();

    const seen: unknown[] = [];
    socket.on<{ participants: number[] }>("presence.state", (payload) => {
      seen.push(payload);
    });
    ws.serverMessage({
      v: 1,
      type: "presence.state",
      id: "f1",
      ts: "2026-01-01T00:00:00.000Z",
      seq: 7,
      payload: { participants: [1, 2] },
    });

    expect(seen).toEqual([{ participants: [1, 2] }]);
    socket.close();

    // A malformed frame is ignored, not fatal.
    const socket2 = makeSocket();
    socket2.connect();
    const ws2 = MockWebSocket.last();
    ws2.serverOpen();
    ws2.onmessage?.({ data: "not json" });
    expect(socket2.getStatus()).toBe("open");
    socket2.close();
  });

  it("reconnects with backoff after a transient drop and replays last_seq", async () => {
    const socket = makeSocket();
    socket.connect();
    const ws1 = MockWebSocket.last();
    ws1.serverOpen();
    ws1.serverMessage({
      v: 1,
      type: "presence.state",
      id: "f1",
      ts: "2026-01-01T00:00:00.000Z",
      seq: 7,
      payload: {},
    });

    ws1.serverClose(1006);
    expect(socket.getStatus()).toBe("reconnecting");

    await vi.advanceTimersByTimeAsync(2_000);
    expect(MockWebSocket.instances).toHaveLength(2);

    const ws2 = MockWebSocket.last();
    ws2.serverOpen();
    expect(socket.getStatus()).toBe("open");
    const firstFrame = JSON.parse(ws2.sent[0] ?? "{}") as {
      type: string;
      payload: { last_seq: number };
    };
    expect(firstFrame.type).toBe("sync");
    expect(firstFrame.payload.last_seq).toBe(7);
    socket.close();
  });

  it("treats fatal close codes as terminal", async () => {
    const socket = makeSocket();
    socket.connect();
    const ws = MockWebSocket.last();
    ws.serverOpen();

    ws.serverClose(4003);
    expect(socket.getStatus()).toBe("failed");

    await vi.advanceTimersByTimeAsync(30_000);
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("retries once with a token refresh on 4001", async () => {
    const { refreshSession } = await import("@/lib/api");
    const socket = makeSocket();
    socket.connect();
    const ws = MockWebSocket.last();
    ws.serverOpen();

    ws.serverClose(4001);
    await flushAsync();

    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(MockWebSocket.instances).toHaveLength(2);
    MockWebSocket.last().serverOpen();
    expect(socket.getStatus()).toBe("open");
    socket.close();
  });

  it("sends heartbeat pings every 25 seconds", () => {
    const socket = makeSocket();
    socket.connect();
    const ws = MockWebSocket.last();
    ws.serverOpen();

    vi.advanceTimersByTime(25_000);
    expect(sentTypes(ws).filter((type) => type === "ping")).toHaveLength(1);

    vi.advanceTimersByTime(50_000);
    expect(sentTypes(ws).filter((type) => type === "ping")).toHaveLength(3);
    socket.close();
  });

  it("does not reconnect after an explicit close", async () => {
    const socket = makeSocket();
    socket.connect();
    const ws = MockWebSocket.last();
    ws.serverOpen();

    socket.close();
    expect(socket.getStatus()).toBe("closed");

    await vi.advanceTimersByTimeAsync(30_000);
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(statuses).not.toContain("reconnecting");
  });
});
