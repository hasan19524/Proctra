# Procto — Decision Records

Lightweight ADRs. Newest last. Each entry: context → decision → consequences.

---

## D1 — SFU selection: LiveKit

**Context.** Procto needs scalable audio/video. The spec forbids building a complicated
SFU from scratch and forbids naive mesh for multi-party meetings.

**Options considered.**

| Option | Assessment |
|---|---|
| **LiveKit** (chosen) | Standalone SFU server (Rust) shipped as a Docker image. Official Python SDK for server-side token minting, official JS/React SDK for the client. Built-in rooms, participants, permissions, connection state, screen share, reconnect handling. |
| mediasoup | A Node.js *library*, not a server. Would require building and maintaining our own Node room/signalling server beside FastAPI — effectively building an SFU layer ourselves. |
| Janus | C gateway, batteries-not-included, heavier ops, weaker Python/JS ergonomics for rooms and permissions. |

**Decision.** Use **LiveKit** as the SFU; FastAPI remains the authority that mints
short-lived, room-scoped LiveKit tokens after authorization.

**Consequences.** Media never touches FastAPI. Two realtime channels must be kept
consistent (documented in REALTIME.md). LiveKit is a required infrastructure service.

---

## D2 — Repository: single monorepo

**Context.** Frontend and backend evolve together, phase by phase, with one Git history.

**Decision.** One repository containing `frontend/`, `backend/`, infra config and docs.

**Consequences.** Simple cross-stack changes and atomic commits; one CI pipeline later;
slightly larger checkout.

---

## D3 — Development: infrastructure in Docker, apps native

**Context.** Hot reload matters most for app code; Postgres/Redis/LiveKit change rarely.

**Decision.** `docker-compose.yml` runs **only** infra. Backend and frontend run natively
via `make dev`. `make dev-full` exists for a clean-machine run.

**Consequences.** Fast edit loop; requires Docker Desktop + native Node/Python on the
developer machine.

---

## D4 — Two realtime channels (app WS vs LiveKit)

**Context.** Chat/presence/controls need persistence, auth, history and replay; media
needs an SFU.

**Decision.** FastAPI WebSocket for application events; LiveKit/WebRTC for media only.

**Consequences.** Clear state ownership (ARCHITECTURE.md §11). The frontend must merge
two streams into one view of the meeting; the backend never fakes media state.

---

## D5 — Database: PostgreSQL, Alembic-owned schema

**Context.** Durable state (users, meetings, messages, notes, audit) needs relations and
strong integrity.

**Decision.** PostgreSQL 16 + SQLAlchemy 2 async + Alembic migrations. Redis holds only
ephemeral coordination data (pub/sub, rate limits, sessions) — never business records.

**Consequences.** Every schema change is a reviewable migration; no hand-edited schema.

---

## D6 — Authentication: access JWT + rotating refresh token

**Context.** Web + WebSocket access with short-lived credentials and revocability.

**Decision.**
- Access JWT (15 min) in memory on the client, also used to authenticate WS upgrades.
- Opaque refresh token, httpOnly cookie, stored **hashed**, rotated on use, revocable.
- Argon2id for passwords.

**Consequences.** No long-lived bearer token in localStorage; WS reconnects must re-mint
access tokens; refresh rotation requires reuse detection (SECURITY.md).

---

## D7 — Python tooling: uv

**Context.** Fast, reproducible Python environment management with lockfile support.

**Decision.** `uv` manages the backend virtualenv and dependency lock
(`backend/uv.lock`), with `ruff` + `mypy` + `pytest` configured in `pyproject.toml`.

**Consequences.** `make setup` is one command; CI can restore from the lockfile.

---

## D8 — Roles vs permissions

**Context.** Spec requires authentication and authorization to be separate concepts.

**Decision.** Authentication = identity (JWT). Authorization = role resolution
(`HOST` / `CO_HOST` / `PARTICIPANT`) + per-meeting permission flags, evaluated in
backend services on every sensitive call. Frontend role checks are cosmetic.

**Consequences.** Slight duplication of checks, but no trust in client-supplied roles.

---

## D9 — No AI/ML in current phases

**Context.** Explicit product constraint.

**Decision.** No LLM, vision, proctoring or behavioural ML code. Phases may add UI
placeholders and extension points only.

**Consequences.** Meeting Assistant (Phase 16) is UI structure only; Exam mode
(Phase 17) is non-ML foundation only.

---

## D10 - Local port allocation (coexistence with other projects)

**Context.** This development machine also runs other projects (e.g. one using host
ports 3000 and 8000 for its own web app and API, and a Postgres on 5433). Procto must
not disturb them (project-owner constraint).

**Decision.** Procto's local development ports are offset:

| Service | Port |
|---|---|
| Next.js dev / prod | **3001** |
| FastAPI | **8001** |
| PostgreSQL (host) | **5434** (container 5432) |
| Redis (host) | **6380** (container 6379) |
| LiveKit | 7880 / 7881 / UDP 50000-50099 |

Wired into: `docker-compose.yml`, `.env.example`, `frontend` dev scripts, `Makefile`,
`scripts/procto.ps1`, and CORS/`NEXT_PUBLIC_*` URLs.

**Consequences.** Procto runs side by side with other stacks without port fights.
Production deployments are unaffected (ports come from environment configuration).

---

## D11 — UI follows the Google Meet reference (layout only)

**Context.** The project owner supplied `reference/` (four Google Meet screenshots)
and directed that Procto's UI must *look like Google Meet* while keeping the already
decided features, tokens and brand.

**Decision.** Meet is the **layout/chrome/pattern reference**, not a visual clone:

- Adopted: home shell (join-code pill, green New CTA, icon rail, date/week strip,
  centered empty state), in-call shell (top bar, featured tile + filmstrip, overlaid
  tile chips, floating pill control dock, bottom-right utility cluster, right-side
  People/Chat panels, emoji reaction bar above the dock).
- Kept: indigo primary, our full token set (incl. `success`/`warning`/`info`),
  Lexend display + Source Sans 3 body, semantic-status rules, all Phase 1 component
  and accessibility requirements.
- Emojis appear only as reaction content, never as UI icons (per DESIGN.md §8).

Recorded in `DESIGN.md` §9 with a per-surface mapping table.

**Consequences.** Screens read as "familiar meeting UI" with Procto branding.
Palette stays indigo-tinted (we did not adopt Google's neutral grays) — revisit only
if the owner asks for a closer color match. Reactions UI ships as visual-only until
Phase 10 (open question in the Phase 1 report).

---

## D12 - Session transport: same-origin proxy + in-memory access token

**Context.** The refresh cookie is httpOnly, SameSite=Lax and scoped to
/api/v1/auth. Browsers drop it for cross-origin requests, so a direct
fetch("http://localhost:8001/...") from the app on :3001 would never carry it.

**Decision.**

- The browser only talks to same-origin /api/v1/*; Next.js rewrites proxy it
  to http://localhost:8001/api/v1/* (see next.config.ts, override with
  API_INTERNAL_URL). Cookies therefore flow on every auth call, and no CORS
  is needed in dev or prod.
- The access JWT lives in module memory (src/lib/api.ts), never in
  localStorage/sessionStorage. On a 401 the client refreshes **once**
  (single-flight) and retries; a failed refresh clears the session.
- Session state is a small React context (SessionProvider) that refreshes on
  first paint; protected routes (/, /room) render a loading gate and
  redirect to /login when no session exists. No zustand/TanStack Query yet -
  plain React state was sufficient for Phase 2; revisit when meeting state
  arrives (Phase 4+).

**Consequences.** Refresh rotation and reuse detection work unchanged from the
browser. WebSocket auth (Phase 4) will pass the access token as a query param
instead, since Next rewrites do not proxy WebSockets (per SECURITY.md).

---

## D13 - Meeting identity: Meet-style short codes, API-owned

**Context.** Meetings need an identifier humans can read aloud, paste into the
join box and share in invites, without exposing sequential IDs.

**Decision.**

- Codes are 11 characters in the shape `xxx-yyy-zzz`, drawn from a 31-char
  alphabet that drops `0/o/1/l` (ambiguity), with a unique index in Postgres
  and up to 5 collision retries per create (`meeting_service`).
- `POST /api/v1/meetings` (auth) creates a meeting in status `waiting`;
  `GET /api/v1/meetings/{code}` (auth) looks it up case-insensitively and
  returns 404 `Meeting not found` otherwise. Lookups are auth-gated like the
  rest of the API; the WS layer (Phase 4) re-checks membership.
- The pre-join lobby requests a **real** `getUserMedia({audio, video})`
  stream, mirrors the preview, toggles `track.enabled` for mic/camera, and
  stops all tracks on unmount; missing or blocked media degrades to an
  initials tile with a clear message instead of failing the join.
- The in-call route is `/room/[code]` and reads the segment with
  `useParams` (client component). The legacy bare `/room` redirects home.
- Host display name pre-fills from the session; joining sends the trimmed
  display name plus mic/camera choices as `JoinOptions`.

**Consequences.** Codes are short enough to speak and type; the unique index
plus retry loop makes collisions a non-event. Lobby media is real, so Phase 9
(LiveKit) can promote the same tracks instead of re-acquiring them.



## D14 - Realtime transport: subscribe-before-broadcast + dedicated pub/sub client

**Status:** Accepted (2026-10-03, Phase 4)

**Context.** The WS gateway fans frames out through Redis pub/sub on
`ws:meeting:{code}`. A subscriber only receives messages published *after*
its SUBSCRIBE completes, and the shared Redis client carries a 2 s
`socket_timeout` that would kill an idle subscription.

**Decision.**
- The gateway subscribes each connection's pub/sub *before* registering
  presence or announcing the join (snapshot -> subscribe -> announce), so no
  connection can miss its own join frame.
- Pub/sub uses a dedicated client (`get_pubsub_client()`) with no
  `socket_timeout`; command traffic (rate limits, presence hashes) keeps the
  shared 2 s-timeout client.
- The handshake runs entirely before `accept` (DB session closed first);
  rejects close with machine-readable codes 4001/4003/4004, idle timeout is
  4013, and the frontend client reconnects with jittered exponential backoff,
  retrying 4001 once after a token refresh.

**Consequences.** Fan-out is race-free and idle listeners survive; the
frontend `src/lib/ws` client owns the 25 s heartbeat, `seq` tracking, and
reconnect policy per REALTIME.md.