/**
 * Meeting WebSocket client (Phase 4).
 *
 * Speaks the v1 envelope from REALTIME.md: `{v, type, id, ts, seq?, payload}`.
 * Next.js rewrites do not proxy WebSockets, so the socket connects directly to
 * `NEXT_PUBLIC_WS_URL` (default `ws://localhost:8001`) with the access token
 * as a query parameter.
 *
 * Reconnect policy: exponential backoff with jitter; auth/protocol rejects
 * (4001/4003/4004/4008) are fatal (except 4001, which retries once after a
 * token refresh); 4013 idle timeout and transient drops reconnect.
 */

import { refreshSession } from "@/lib/api";

export type WsStatus = "connecting" | "open" | "reconnecting" | "closed" | "failed";

export interface WsEnvelope<P = unknown> {
  v: number;
  type: string;
  id: string;
  ts: string;
  seq?: number;
  payload: P;
}

const PROTOCOL_VERSION = 1;
const HEARTBEAT_MS = 25_000;
const BACKOFF_BASE_MS = 400;
const BACKOFF_MAX_MS = 15_000;
/** Close codes that mean "do not blindly retry" (REALTIME.md §error codes). */
const FATAL_CLOSE_CODES = new Set([4001, 4003, 4004, 4008]);
const CLOSE_UNAUTHORIZED = 4001;

export function meetingWsUrl(code: string, accessToken: string): string {
  const base = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8001").replace(/\/+$/, "");
  return `${base}/api/v1/ws/meetings/${encodeURIComponent(code)}?token=${encodeURIComponent(accessToken)}`;
}

/** Random id used for frame ids and client-side idempotency keys. */
export function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function buildFrame(type: string, payload: unknown = {}): WsEnvelope {
  return {
    v: PROTOCOL_VERSION,
    type,
    id: newId(),
    ts: new Date().toISOString(),
    payload,
  };
}

type FrameHandler = (payload: unknown, frame: WsEnvelope) => void;

export class MeetingSocket {
  private readonly code: string;
  private readonly getToken: () => string | null;
  private ws: WebSocket | null = null;
  private status: WsStatus = "closed";
  private shouldRun = false;
  private attempt = 0;
  private refreshedForAuth = false;
  private lastSeq = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private outbox: string[] = [];
  private readonly handlers = new Map<string, Set<FrameHandler>>();
  private readonly statusHandlers = new Set<(status: WsStatus) => void>();

  constructor(code: string, getToken: () => string | null) {
    this.code = code;
    this.getToken = getToken;
  }

  getStatus(): WsStatus {
    return this.status;
  }

  connect(): void {
    if (this.shouldRun) return;
    this.shouldRun = true;
    this.open();
  }

  close(): void {
    this.shouldRun = false;
    this.clearTimers();
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        ws.close(1000);
      } catch {
        // already closed
      }
    }
    this.setStatus("closed");
  }

  /** Subscribe to a server event type; returns an unsubscribe function. */
  on<P = unknown>(type: string, handler: (payload: P, frame: WsEnvelope<P>) => void): () => void {
    const wrapped = handler as unknown as FrameHandler;
    let set = this.handlers.get(type);
    if (!set) {
      set = new Set();
      this.handlers.set(type, set);
    }
    set.add(wrapped);
    return () => {
      set?.delete(wrapped);
    };
  }

  /** Subscribe to connection status changes; returns an unsubscribe function. */
  onStatus(handler: (status: WsStatus) => void): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  /**
   * Send a client frame. Queued while the socket is connecting and flushed on
   * open; returns the frame id, or null when the socket is not intended to run.
   */
  send(type: string, payload: unknown = {}): string | null {
    if (!this.shouldRun) return null;
    const frame = buildFrame(type, payload);
    const data = JSON.stringify(frame);
    if (this.ws && this.ws.readyState === 1) {
      this.ws.send(data);
    } else {
      this.outbox.push(data);
    }
    return frame.id;
  }

  private setStatus(next: WsStatus): void {
    if (this.status === next) return;
    this.status = next;
    for (const handler of [...this.statusHandlers]) {
      handler(next);
    }
  }

  private open(): void {
    if (!this.shouldRun) return;
    const token = this.getToken();
    if (!token) {
      this.shouldRun = false;
      this.setStatus("failed");
      return;
    }
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(meetingWsUrl(this.code, token));
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      if (!this.shouldRun || this.ws !== ws) {
        ws.close();
        return;
      }
      this.attempt = 0;
      this.refreshedForAuth = false;
      this.setStatus("open");
      this.startHeartbeat();
      ws.send(JSON.stringify(buildFrame("sync", { last_seq: this.lastSeq })));
      if (this.outbox.length > 0) {
        for (const data of this.outbox) ws.send(data);
        this.outbox = [];
      }
    };

    ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };

    ws.onerror = () => {
      // onclose always follows; handled there.
    };

    ws.onclose = (event) => {
      this.stopHeartbeat();
      if (this.ws === ws) this.ws = null;
      if (!this.shouldRun) {
        this.setStatus("closed");
        return;
      }
      if (event.code === CLOSE_UNAUTHORIZED && !this.refreshedForAuth) {
        this.refreshedForAuth = true;
        void this.refreshAndRetry();
        return;
      }
      if (FATAL_CLOSE_CODES.has(event.code)) {
        this.shouldRun = false;
        this.setStatus("failed");
        return;
      }
      this.scheduleReconnect();
    };
  }

  private async refreshAndRetry(): Promise<void> {
    this.setStatus("reconnecting");
    try {
      await refreshSession();
    } catch {
      this.shouldRun = false;
      this.setStatus("failed");
      return;
    }
    this.open();
  }

  private handleMessage(data: unknown): void {
    if (typeof data !== "string") return;
    let frame: WsEnvelope;
    try {
      frame = JSON.parse(data) as WsEnvelope;
    } catch {
      return;
    }
    if (!frame || typeof frame.type !== "string") return;
    if (typeof frame.seq === "number" && Number.isFinite(frame.seq)) {
      this.lastSeq = Math.max(this.lastSeq, frame.seq);
    }
    const handlers = this.handlers.get(frame.type);
    if (handlers) {
      for (const handler of [...handlers]) {
        handler(frame.payload, frame);
      }
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldRun || this.reconnectTimer) return;
    this.setStatus("reconnecting");
    this.attempt += 1;
    const exponential = Math.min(BACKOFF_BASE_MS * 2 ** (this.attempt - 1), BACKOFF_MAX_MS);
    const jittered = Math.round(exponential * (0.5 + Math.random() * 0.5));
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, jittered);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send("ping");
    }, HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearTimers(): void {
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.outbox = [];
  }
}
