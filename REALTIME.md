# Procto — Realtime

Two realtime channels. This split is intentional and must be preserved.

| Channel | Transport | Carries | Owner |
|---|---|---|---|
| **App realtime** | WebSocket (FastAPI) | presence, chat, reactions, hand raise, host controls, waiting room, permissions | backend |
| **Media realtime** | WebRTC (LiveKit SFU) | audio, video, screen share, track state, connection quality | LiveKit |

## 1. App WebSocket

### Endpoint

```text
GET /api/v1/ws/meetings/{meeting_id}?token=<access_jwt>   → 101 Switching Protocols
```

### Connect lifecycle

```text
1. HTTP upgrade request + access token
2. Backend validates JWT signature/expiry
3. Backend loads meeting, checks: exists, not ended, not locked,
   membership / waiting-room state
4. On success  → register connection in the in-memory registry
              → subscribe to Redis channel ws:meeting:{meeting_id}
              → send  server: sync.state  (full snapshot: participants, chat tail)
5. On failure  → close with a machine-readable reason code
```

### Envelope

Every frame is JSON:

```json
{
  "v": 1,
  "type": "chat.message",
  "id": "5f0c9e0a-...-client-generated for c2s, server-generated for s2c",
  "seq": 148,
  "ts": "2026-10-03T12:00:00.000Z",
  "payload": { }
}
```

- `v` — protocol version, bumped only on breaking change.
- `type` — dotted namespaced event name.
- `id` — idempotency key. Client-generated for client→server frames so retries are
  safe; server-generated for broadcasts.
- `seq` — per-meeting monotonic sequence **server-assigned** on durable events.
  Used for reconnect replay.
- Absent `seq` means the event is ephemeral (typing, reaction burst) and is not replayed.

### Client → Server events

| type | payload (summary) | replayed? |
|---|---|---|
| `ping` | – | no |
| `sync` | `last_seq` | request |
| `presence.update` | mic/camera/hand flags | no |
| `chat.send` | `body`, `client_id`, `reply_to`, `recipient_id?` | persisted → yes |
| `reaction.send` | `emoji` | no |
| `hand.raise` / `hand.lower` | – | folded into presence |
| `host.action` | `action` = lock, end, mute_participant, remove, permission toggle, waiting-room approve/deny | persisted where durable |

### Server → Client events

| type | payload (summary) |
|---|---|
| `error` | `code`, `message`, `retryable` |
| `pong` | – |
| `sync.state` | full snapshot after connect/reconnect |
| `presence.state` | participant list + flags |
| `participant.joined` / `participant.left` | participant summary |
| `chat.message` | persisted message incl. `seq` |
| `chat.deleted` | message id |
| `reaction.burst` | emoji + participant ids |
| `permission.changed` | meeting/participant permission delta |
| `meeting.ended` / `meeting.locked` | terminal / policy events |
| `waiting_room.admitted` | – |

### Delivery guarantees

- **Chat**: at-least-once. Server persists first, then broadcasts. The client tracks a
  `client_id` → status map (`sending` / `sent` / `failed`) so the UI shows real delivery
  state and a failed send is retried with the same `client_id` (server deduplicates).
- **Reconnect replay**: on `sync { last_seq }` the server re-sends durable events with
  `seq > last_seq` from Postgres. Chat must survive transient network loss.
- **Ephemeral events** (presence, reactions, typing) are not replayed; `sync.state`
  restores the snapshot instead.
- **Heartbeat**: client sends `ping` every 25 s, expects `pong`; missed pongs trigger
  reconnect with exponential backoff + jitter.

### Multi-worker fan-out

The in-memory registry handles one worker. Cross-worker delivery goes through Redis
pub/sub on `ws:meeting:{meeting_id}`: a worker receiving a frame publishes it, and every
worker subscribed to that channel broadcasts to its local connections.

## 2. Media (LiveKit)

The backend mints a LiveKit JWT after authorization:

```text
sub   = user id or guest identity
room  = meeting_id
grants: canPublish, canPublishData, canSubscribe, canRecord=false
ttl   = short (meeting-scoped, re-minted on reconnect)
```

Client uses `livekit-client` / `@livekit/components-react` to:

- connect, publish camera + microphone,
- publish screen share (`unpublish` to stop),
- observe `ConnectionState`, active speaker, participant track states,
- mirror participant connect/disconnect into the app WS presence layer.

**Rule:** media state is authoritative in LiveKit; the app WS presence layer is a
read-model for UI. The backend never fakes media state.

## 3. Reconnect matrix (summary)

| Failure | Handling |
|---|---|
| WS disconnect | auto-reconnect w/ backoff → `sync { last_seq }` → replay + snapshot |
| LiveKit disconnect | LiveKit SDK reconnect/resume; re-mint token if expired |
| Browser refresh | full re-join: auth → join API → LiveKit token → `sync.state` |
| Camera/mic device lost | device change events → UI state + republish |
| Meeting ended / locked / expired | server sends terminal event → UI blocks re-entry |

Detailed UX belongs to Phase 14; the protocol above is the foundation it builds on.
