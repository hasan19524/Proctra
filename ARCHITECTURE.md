# Procto — Architecture

> Phase 0 document. Keep this updated whenever an architectural decision changes.

## 1. System overview

```text
                        ┌──────────────────────┐
                        │   Next.js Frontend   │
                        │  (React/TS/Tailwind) │
                        └─────┬──────────┬─────┘
                    REST/API  │          │  WebSocket (app events)
                              ▼          ▼
                   ┌─────────────────────────────┐
                   │     FastAPI Backend (Py)    │
                   │  REST · Auth · WS gateway   │
                   └────┬───────────┬────────────┘
                        │           │
              ┌─────────▼──┐   ┌────▼─────┐   ┌──────────────┐
              │ PostgreSQL │   │  Redis   │   │  LiveKit SFU │
              │ (durable)  │   │ sessions,│   │  (media only)│
              └────────────┘   │ ratelimit│   └──────▲───────┘
                               │ pub/sub  │          │ WebRTC
                               └──────────┘     ┌────┴─────┐
                                                │ Frontend │
                                                └──────────┘
```

### Two realtime channels (deliberate)

| Channel | Carries | Why it is separate |
|---|---|---|
| FastAPI WebSocket | chat, presence, host controls, waiting room, reactions, permissions | needs persistence, auth, history, reconnect replay |
| LiveKit (WebRTC) | audio, video, screen share, track subscribe/publish | needs SFU-grade low-latency media routing |

This enforces the project principle **database state ≠ realtime state ≠ WebRTC state**.

## 2. Product structure

All three entry points (Create / Join / Exam-Interview) funnel into one **Meeting Core**.
There is exactly **one** implementation of a meeting; Exam/Interview mode configures it.

```text
Create Meet ─┐
Join Meet ───┼─► Meeting Core ─► WebRTC · Chat · Notes · Participants · Host controls
Exam/Int. ───┘
```

## 3. Frontend architecture

- **Next.js App Router**, TypeScript strict mode.
- `src/app` — routes (route groups for `(auth)`, `(dashboard)`, `(meeting)`).
- `src/components/ui` — shadcn/ui primitives (design system, Phase 1).
- `src/components/<domain>` — feature components; no giant files.
- `src/lib/api` — typed REST client (fetch wrapper, access-token injection).
- `src/lib/ws` — WebSocket client with reconnect + event envelope handling.
- `src/lib/livekit` — LiveKit room provider/connection helpers.
- `src/lib/proctor` — client-side proctoring: self-hosted MediaPipe face landmarker,
  pure signal classifier (`detector.ts`), camera sampling `engine.ts`.
- `src/stores` — Zustand stores (session, meeting UI state).
- `src/hooks` — reusable hooks, incl. `use-proctoring` (exam proctoring lifecycle,
  tab-visibility signal, prejoin self-check).
- Server state fetched via TanStack Query; ephemeral UI state in Zustand.

Frontend role checks are **UX only**. Authorization is enforced by the backend.

## 4. Backend architecture

```text
backend/app/
├── main.py          # FastAPI app factory, router mounting, lifespan
├── core/            # config (pydantic-settings), security, deps, logging, errors
├── api/v1/          # HTTP routers: health, auth, meetings, ...
├── ws/              # WebSocket gateway: connect auth, event registry, handlers
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response contracts
├── services/        # business logic (auth, meeting, chat, proctor) — routers stay thin
└── db/              # engine, session, base, alembic env
```

Layering rule:

```text
router/ws handler  →  service  →  model/repository
        (validation)   (business rules + authorization)
```

- Routers and WS handlers do **input validation + orchestration only**.
- Services own business rules, permission checks and persistence.
- Every mutating operation re-checks authorization **server-side**.

## 5. Database architecture

PostgreSQL is the **source of truth for durable state only**. Ephemeral state (who is
connected right now, mic status, typing, reaction bursts) lives in Redis / the in-memory
WS registry / LiveKit and is *never* written to Postgres except as history
(messages, participant join/leave records, meeting results).

Full schema and conventions: [DATABASE.md](./DATABASE.md).

## 6. Authentication architecture

- Email + password, **Argon2id** hashing.
- **Access JWT** — short-lived (15 min), held in frontend memory.
- **Refresh token** — rotated on use, stored hashed in Postgres, delivered in an
  httpOnly cookie.
- WebSocket auth: access token as connect query parameter, validated server-side on
  upgrade.
- LiveKit access token: minted by FastAPI **only after** password/waiting-room/lock/
  membership checks pass. Grants are scoped to a single room and identity.

Details: [SECURITY.md](./SECURITY.md).

## 7. WebSocket (application) architecture

- Endpoint: `GET /api/v1/ws/meetings/{meeting_id}?token=<access_jwt>` (WebSocket upgrade).
- On connect: authenticate → authorize membership → register in the in-memory registry
  → subscribe to the Redis pub/sub channel for that meeting (multi-worker safe).
- All frames use a versioned JSON envelope; see [REALTIME.md](./REALTIME.md).
- Reconnect: the client sends `sync` with the last processed sequence and the server
  replays durable events (chat) so messages are not lost on transient network failures.

### Exam proctoring pipeline

Exam meetings (`meetings.kind = 'exam'` with `proctoring_enabled`) add integrity
signalling on the same socket. Detection is client-side; scoring, persistence and
fan-out are server-side:

```text
hidden <video>  →  MediaPipe landmarker (2 Hz, self-hosted WASM, on-device)
               →  classified signal (looking_away | no_face | multiple_faces |
                                     speaking | eyes_closed | tab_hidden | video_blur)
               →  WS client frame  proctor.event {signal, duration_s, detail}
               →  gateway: exam + proctoring gate, host exempt, signal whitelist,
                  30/min per (user, meeting)
               →  proctor_service.record_event → proctor_events
                  (points + meeting minute computed server-side)
               →  WS server frame  proctor.flag  (host-only fan-out)
               →  Integrity panel / GET /meetings/{code}/report(.csv) (host-only)
```

Video frames never leave the device — only signal labels cross the wire
(see [SECURITY.md](./SECURITY.md) §6). Students never receive `proctor.flag` frames or
the `proctor_flags` snapshot field.

## 8. WebRTC / SFU architecture

**SFU: LiveKit** (see [DECISIONS.md](./DECISIONS.md) for the comparison against mediasoup
and Janus). Star topology — every participant publishes to the SFU and subscribes to the
SFU. No mesh peer-to-peer anywhere.

```text
join flow:

1. Client authenticates against FastAPI (REST)
2. FastAPI validates: meeting exists, not ended, not locked,
   password OK, waiting-room state, participant permissions
3. FastAPI mints a LiveKit token  { identity, room, publish grants }
4. Client connects to LiveKit with that token
5. LiveKit publishes/subscribes audio, video, screen share
6. LiveKit participant events are mirrored into the app WS presence layer
```

State ownership:

| State | Owner |
|---|---|
| tracks, connection quality, screen share stream | LiveKit |
| roles, permissions, lock, waiting room, password | FastAPI (Postgres) |
| chat, presence feed | FastAPI WS + Postgres (history) |
| proctoring events, integrity score/report | FastAPI (Postgres; the client only classifies video on-device) |
| view of all of the above | frontend (derived) |

## 9. Storage architecture

- **Postgres** — users, meetings, participants history, messages, notes, audit logs,
  proctor events (signal labels only, no media).
- **Redis** — refresh-session metadata, rate-limit counters, WS pub/sub fan-out.
- **LiveKit** — ephemeral media only; it stores nothing durable.
- Uploaded files (chat attachments, Phase 9): local disk volume initially, behind a
  `storage` interface so object storage can replace it later.
- No server-side AI/ML processing and no media storage: the proctoring vision model runs
  on-device in the browser; only classified signal labels are persisted.

## 10. Deployment architecture

Local development today (Phase 0):

- Docker Compose runs **infrastructure only**: `postgres`, `redis`, `livekit`.
- `backend` and `frontend` run natively with hot reload (`make dev`).
- `make dev-full` runs everything in Docker when a clean-machine run is needed.

Production (future, not implemented): same images, containerized backend/frontend,
managed Postgres/Redis, LiveKit cluster behind UDP load balancer, secrets from the
environment. Not part of the current phases.

## 11. State categories (project principle #7)

```text
Persistent DB state   users, meetings, messages, notes, audit, proctor events
Backend runtime state WS registry (connection id → user/meeting)
Redis state           pub/sub channels, rate-limit counters, sessions
WebRTC state          tracks, publishers, subscribers, quality (LiveKit)
Frontend state        router/view, local media devices, optimistic UI
```

Never promote an ephemeral value into the database as if it were durable truth, and
never trust a frontend-provided value as authority.
