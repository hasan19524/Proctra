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

## D15 - Chat delivery: persist-first, client_id idempotency, bounded replay

**Status:** Accepted (2026-10-04, Phase 5)

**Context.** REALTIME.md requires at-least-once chat: the server persists
before broadcasting, and reconnects replay durable events from Postgres by
`seq`. Naive replay can flood a fresh client or duplicate frames the client
already has.

**Decision.**
- `chat.send` validates (1-4000 chars), allocates the Redis-backed
  per-meeting `seq`, inserts into `meeting_messages`, and only then
  broadcasts `chat.message`; failures return a retryable `internal_error`.
- The client supplies `client_id` (UUID) as an idempotency key; a partial
  unique index on `(meeting_id, client_id)` makes retries return the
  existing row while still re-broadcasting (at-least-once).
- `sync.state` carries a 50-message tail (fresh joins need no replay);
  `sync {last_seq}` replays `seq > last_seq` only when `last_seq > 0`,
  capped at 500 messages. The frontend merges frames by id, ordered by seq.

**Consequences.** Chat survives transient network loss and duplicated
delivery without unbounded history dumps; deletion (`chat.deleted`) arrives
with host controls in Phase 6.
---

## D16 - Host controls: DB authority, terminal frames before kick, presence attendance

**Status:** Accepted (2026-10-04, Phase 6)

**Context.** Host actions (lock/end, mute, remove, permissions) must be
authoritative, race-free, and survive multi-worker fan-out. Application-initiated
disconnects also have to be observable by tests and by the removed client.

**Decision.**
- Every `host.action` re-derives the caller's role from Postgres inside a fresh
  session (never the handshake copy); failures return `forbidden`,
  `invalid_target`, `not_found`, or `unknown_action`.
- Terminal frames are *direct-sent to local sockets before* `kick` + close
  (4003): `kick: asyncio.Event` on `LocalConnection` wakes a pending
  `websocket.receive` (the ASGI test client does not wake it on app-initiated
  close), then the same frame is published on pub/sub for other workers �
  clients treat `meeting.ended`/`participant.removed` idempotently.
- "Remove" disconnects only (Meet parity): a removed user can rejoin while the
  meeting is unlocked. Attendance is persisted per join/leave in
  `meeting_participants`; waiting-room admission, chat deletion, and audit logs
  are deferred to Phase 13.
- Per-meeting permissions (`allow_chat`/`allow_reactions`/`allow_screen_share`,
  default true) live on `meetings`, are enforced server-side on the matching
  action, and broadcast as `permission.changed`.

**Consequences.** Lock/end/remove behave identically across workers and are
covered by an in-suite WS test client plus the real-socket smoke; the frontend
derives its gates from `sync.state.meeting` plus those broadcasts instead of
optimistic local state.

---

## D17 - Notes: whole-document WS saves, two visibility documents, relay-level filtering

**Status:** Accepted (2026-10-04, Phase 7)

**Context.** Notes are a persistent JSONB document per meeting (DATABASE.md),
not a message log. The spec calls the content a "rich text document" but no
editor is in the dependency set, and concurrent keystroke streaming would
need CRDTs the spec never asks for.

**Decision.**
- `meeting_notes` holds up to two whole documents per meeting (`all` and
  `host_only`, UNIQUE per pair). Saves go over the existing socket as
  `note.save {visibility, content}` and broadcast `note.updated`; `sync.state`
  re-seeds late joiners � same transport and membership checks as chat.
- Content shape is `{"text": "<string>"}` inside JSONB � schema-compatible
  with a future rich-text structure without one now; saves are explicit
  (Save button), last-write-wins, capped at 100k characters (`invalid_note`).
- `host_only` is enforced in three places: save authorization (host role
  re-derived like `host.action`), snapshot filtering (non-hosts never receive
  one), and relay-level frame filtering (`_is_host_only_note` in the gateway's
  per-connection relay and broadcast fallback) so pub/sub fan-out cannot leak
  a private document.
- The panel derives editor state in render: drafts adopt server-confirmed
  content only while clean, and `dirty` clears solely on an echo matching the
  draft � a rejected save therefore stays visibly unsaved.

**Consequences.** Notes are durable, reconnect-safe, and private by default;
upgrading to a real collaborative editor later means changing the content
shape and save cadence, not the transport or the visibility model.

---

## D18 - Reactions are transient; hand raise is presence state

**Status:** Accepted (2026-10-04, Phase 8)

**Context.** Two features look similar in the UI but have opposite
persistence needs: burst reactions (spammy, must never hit Postgres) and the
raised hand (must survive reconnects and show up in snapshots).

**Decision.**
- Reactions travel as `reaction.send {label}` and fan out as
  `reaction.received {user_id, name, label}` with no `seq` and no row �
  invalidation is a server-side whitelist (the nine ReactionBar labels) plus
  the meeting's `allow_reactions` gate (`permission_denied` when off).
  Clients keep a capped, TTL-pruned list; the CSS float animation
  (`reaction-float`, `animation-fill-mode: forwards`) hides items after ~4s,
  so rendering stays pure (no `Date.now()` in render � `react-hooks/purity`).
- Hand raise is just a `presence.update {hand_raised}` flag: the UI derives
  it from the roster (never local state), so every participant, the
  `sync.state` snapshot, and a rejoining user all agree.

**Consequences.** Reactions cannot leak load into the database or the replay
path; the hand persists exactly as long as presence does, and Phase 13 can
rate-limit `reaction.send` without touching a storage model.

---

## D19 - LiveKit is the media path; the app API mints join tokens

**Status:** Accepted (2026-10-04, Phase 9)

**Context.** The meeting socket already carries roster, chat, notes, and
controls, but real audio/video must go through an SFU (ARCHITECTURE.md 8).
Someone has to hand a browser a short-lived, room-scoped credential without
letting the client forge grants.

**Decision.**
- `POST /api/v1/meetings/{code}/token` mints the JWT server-side with
  `livekit-api` (`AccessToken` + `VideoGrants(room_join)`), identity =
  `str(user.id)`, name = display name, TTL 10 minutes. The API is the only
  holder of the LiveKit API key/secret (`config.py`, `.env`).
- Gates mirror the socket: 404 unknown code, 403 `ended`, 403 `locked` for
  non-hosts - a rejected token endpoint is the same admission control as a
  rejected WS join.
- The frontend runs ONE `Room` per call via `useLiveKitRoom(code, micOn,
  cameraOn)` beside the app WS: roster/presence stays on the app socket, only
  media rides the SFU. Mic/camera flags push into LiveKit publications after
  connect; tiles are projected as `MediaTile {id, name, isLocal, cameraTrack,
  audioTrack}` keyed by identity = user id so they line up with roster rows.
- Two rosters coexist by design: WS presence is authoritative for UI
  (mute/hand/host flags, reconnect snapshots); LiveKit publications are
  authoritative for media (a tile shows video only when an unmuted camera
  publication exists). D19 keeps them from having to agree beyond the shared
  identity key.
- Known caveat: identity = user id means a second tab for the same account
  joins the LiveKit room as a duplicate identity (SFU second-connection wins
  media). Multi-tab handling is deferred to Phase 12/15 if it shows up in E2E.

**Consequences.** Grants can never outlive the meeting state (lock/end cut
off new tokens even for open sockets of past tabs), the secret never reaches
the browser, and swapping SFU vendors means changing only the token service
and `useLiveKitRoom`.

---

## D20 - Screen share: roster flag over the app socket, media over LiveKit

**Status:** Accepted (2026-10-04, Phase 10)

**Context.** Like chat vs. media in D19, screen sharing has two halves: the
SFU publication (real pixels) and the social signal (who is presenting,
is the host allowing it). They must agree without introducing a third
transport.

**Decision.**
- Media: the sharer publishes `Track.Source.ScreenShare` through the existing
  LiveKit room; `useLiveKitRoom.toggleScreenShare()` resolves to the new
  on/off state (null when the browser picker is declined or the room is not
  ready) and "am I sharing" is *derived* from the local publication - the OS
  can stop a share outside our UI (ESC, OS shortcut), so mirrored state would
  lie.
- Signal: `presence.update {screen_share_on}` rides the app socket like
  mic/hand flags (default false, boolean-only merge). The gateway re-reads
  the meeting row before accepting `screen_share_on: true` - a connection-scoped
  Meeting is stale the moment a host flips `set_permissions`, which is the
  same fresh-read pattern chat and reactions already use.
- Enforcement is layered: the button shows a toast and does nothing when
  `allow_screen_share` is off, the server rejects the roster flag with
  `permission_denied`, and if the host disables mid-share an effect
  force-stops the local publication (fires once per disable) so pixels and
  permission cannot drift apart.
- UI: an active share promotes to the main stage ("X is presenting"); every
  camera - including the presenter's - moves to the strip. The presenter is
  found by identity in the WS roster, keeping D19's two-roster rule.

**Consequences.** Host permission is enforced at every layer that matters
without LiveKit server-side webhooks; a declined OS prompt costs a toast, not
a desync; and "who is presenting" survives reconnects because it lives in the
presence snapshot.

---

## D21 - Meeting experience layer: shortcuts, speaker rings, pinning, ending

**Status:** Accepted (2026-10-27, Phase 11)

**Context.** The core product (media, chat, notes, controls) worked, but the
call shell still carried Phase 1 placeholders: shortcut labels with no
handlers, a pin button with no onClick, a "Meeting details (demo)" toast, and
no way for a host to end a meeting from the UI.

**Decision.**
- Shortcuts (M/V/S/C/R) are owned by `InCallView` - it already holds the
  handlers and the chat panel state. The listener ignores events while the
  target is an input/textarea/contenteditable, so typing in chat never
  triggers them, and the S key routes through the same
  `canScreenShare` gate as the button (one toast, one truth).
- Speaker rings come from LiveKit `ActiveSpeakersChanged` (identities only -
  `speakingIds`), projected onto roster tiles by user id per D19's dual-roster
  rule. Presence stays authoritative for flags; the SFU is authoritative for
  "whose mic is hot right now".
- Pinning is view-local state (`pinnedId`) with render-phase derivation: a
  pin dies when its participant leaves, no effect needed. Stage precedence is
  share > pinned > self; whoever is off-stage moves into the strip, so no
  camera ever disappears.
- Ending a meeting is host-only (menu item hidden otherwise) and always
  double-checked with an AlertDialog before `host.action end` goes out -
  it is the one irreversible action in the product.
- The details dialog shows real data (title, code, invite URL copied via the
  clipboard API) instead of the demo toast; clipboard failure toasts an
  error rather than failing silently.

**Consequences.** The call shell now behaves like the product the spec
describes with no dead controls left behind; every placeholder removed here
was a UI-only stub, so no backend contract changed in this phase.

---

## D22 - Failures are bounded and recoverable, never silent

**Status:** Accepted (2026-10-27, Phase 12)

**Context.** The reconnect matrix in REALTIME.md 3 promised behavior the
code did not fully deliver: the WS side already did backoff + `last_seq`
replay (D14), but the LiveKit side minted one token at mount and, if the
first handshake failed or the session died later, dropped straight to a
permanent "media unavailable" - even though a fresh 10-minute token costs
one HTTP round trip.

**Decision.**
- The LiveKit hook now has exactly two recovery bounds: the initial
  handshake retries once with a freshly minted token, and a session that
  existed gets exactly one re-mint + reconnect after LiveKit gives up.
  A second death is terminal (chat-only, warning toast). No retry loops,
  no retry storms.
- Every attempt builds its own `Room`; a socket poisoned by a failed
  handshake is detached and discarded rather than reused. Handler wiring
  is tracked per-Room so cleanup detaches every generation, not just the
  last one.
- The recovery state machine is explicit in the status field the UI
  already renders: `connecting -> connected -> reconnecting -> connected`
  or `... -> failed`. Before a session exists, connection-state noise from
  a failed attempt is ignored - the handshake loop alone reports failure,
  so a transient blip never flashes a false "failed" at the user.
- Server side the matrix was already true, so Phase 12 proves it with
  tests instead of new code: idle sockets close 4013 and may rejoin
  immediately; an abrupt drop releases presence and attendance
  (`left_at`), and the rejoin gets a snapshot whose tail still holds the
  messages sent before the drop.

**Consequences.** Every failure mode in the product now ends in a defined
state - recovered, or visibly failed with chat still working - and the
bounded-retry contract is pinned by tests on both sides, so future phases
cannot silently regress it.

---

## D23 - Proctoring: self-hosted client-side vision, server-authoritative scoring

**Status:** Accepted (2026-10-29, Phase 16)

**Context.** Exam mode needs integrity signals (looking away, no face, multiple
faces, speaking, eyes closed, tab hidden, video blur). Server-side video
analysis would mean streaming camera frames to the backend - a privacy
liability and a second media pipeline beside LiveKit (D1/D4) - while a cloud
vision API would add an API-key dependency and per-call cost. At the same
time, a purely client-computed integrity score would be trivially forgeable
in the student's own browser. (Supersedes the blanket no-ML stance in D9 for
proctoring only.)

**Decision.**
- Detection runs entirely on-device: a self-hosted MediaPipe face landmarker
  (WASM + model served from `frontend/public`, no CDN, no API keys) samples a
  hidden `<video>` at 2 Hz and classifies signals in a pure, unit-tested
  detector (`src/lib/proctor/detector.ts`) with per-signal min-active debounce
  and cooldown hysteresis, so a blink is not "eyes_closed" and a glance is not
  "looking_away".
- The client only *reports observations*: `proctor.event {signal, duration_s,
  detail}` over the existing app socket (D4). It never sends a score.
- The server owns truth: the gateway accepts events only for exam meetings
  with proctoring enabled, exempts the host, whitelists the signal set,
  rate-limits (30/min per user+meeting), and `proctor_service.record_event`
  computes points from the server-side `PROCTOR_SIGNALS` table plus the
  meeting minute, then persists to `proctor_events`. Hosts get live
  `proctor.flag` frames (host-only fan-out via the relay-filter pattern from
  D17) and a host-only report endpoint graded against the `meeting_invites`
  roster.

**Consequences.** Video never leaves the student's device (privacy story in
SECURITY.md) and there are no third-party vision dependencies; the frontend
image grows by ~44 MB of static WASM/model assets that the browser downloads
lazily (only the variant it needs). The score is never client-authoritative,
so tampering with the JS changes observations, not grades - and a determined
student can still evade an on-device detector, which is a known limit of any
client-side proctoring, not a defect of this design.

## D24 - Object storage: provider-independent abstraction, MinIO dev / R2 prod

**Context.** Evidence clips, student screenshots, and meeting attachments need
durable binary storage. Tests and local demonstrations must run with no cloud
credentials, subscriptions, or internet access (D10's self-contained dev
environment), while cloud deployment needs a managed private store with
server-side authorization. Binding business logic to either vendor would make
the other environment untestable.

**Decision.**
- The backend talks to a single `ObjectStorage` ABC (`app/storage/base.py`:
  put / stat / exists / open (Range) / delete / presign, plus idempotent
  ensure-bucket) and never imports a concrete provider outside that package.
- Two S3-compatible providers share one wire implementation
  (`S3CompatibleStorage`): `MinIOStorage` (path-style, plain HTTP,
  localhost:9000, a Docker Compose service) and `R2Storage` (Cloudflare
  virtual-hosted endpoint, region `auto`).
  `STORAGE_PROVIDER=minio|r2` selects at startup; `build_storage()` validates
  eagerly so the lifespan fails fast with a precise message (r2 without its
  R2_* credentials, minio in production, empty endpoint). boto3 runs behind
  `run_in_threadpool`, keeping storage I/O off the event loop.
- PostgreSQL is the source of truth: `stored_files` holds purpose, MIME, size,
  the storage *key* (never a provider URL), `upload_status`
  (pending -> uploaded | failed, then missing -> deleted -> purged), the
  retention deadline, and `legal_hold`. A partial unique index enforces one
  active clip per proctoring event.
- Reads are proxied through the backend by default: server-side authorization
  on every request (owner or host), Range support for video seeking, an audit
  row per access, and the strict CSP untouched. Short-lived presigned URLs
  exist behind an authorized endpoint for API consumers; hold is host-only.
- Uploads sniff magic bytes (the declared Content-Type is ignored), enforce
  per-purpose caps (clip 50 MB, screenshot 10 MB, attachment 25 MB) behind a
  Content-Length pre-check, and persist `failed` rows on storage errors so
  reports show gaps honestly instead of pretending they never happened.
  The retention sweep (background loop, sleep-first) purges expired files but
  skips `legal_hold`; deletion tombstones the row and removes the object,
  with the sweep retrying any failed removal.

**Consequences.** Development and tests need only `docker compose up -d
minio` - no Cloudflare account, credentials, or internet - and the identical
code path runs against R2 in production by flipping environment variables.
Switching providers later is an object migration (`aws s3 sync`), not a code
change, because records store keys rather than URLs. MinIO CE is end-of-life
and its Docker Hub image was deleted (Sept 2026), so compose pins
`bitnamilegacy/minio`, the last anonymously pullable image of the AGPL server;
the abstraction means replacing that image later is a one-line compose change.


## D25 - Invites are the link: no email dependency

**Context.** Phase 1 planned G3 invite emails (SMTP via a Gmail app password), but the
product's real invite path is already a shared meeting link with an optional password
(the PreJoinLobby gate): the host pastes `/room/<code>` into chat, exactly like a meet
link. The deployer is a student at $0 with no credit card, so every extra account
(DuckDNS aside) adds friction, and consumer-SMTP delivery to spam folders is unreliable
anyway. Two flow gaps existed: unauthenticated visitors opening a room link were bounced
to `/login` and lost their destination, and the in-call "Add people" button was a demo
toast.

**Decision.**
- Invites are **the link**: `/room/<code>` plus the meeting/exam password when set is the
  only invite mechanism. G3 invite-email delivery is descoped from launch scope; no SMTP,
  no `SMTP_*` env vars, no mailer code, no Gmail account. `MeetingInvite` stays exactly
  what it is today - report roster metadata (PRESENT/ABSENT rows built by
  `proctor_service.build_report`) - and never implies delivery.
- Unauthenticated visits preserve the destination: gated views redirect to
  `/login?next=<path>`; `login` and `register` honour `?next=` and carry it across the
  login/register hop. `next` is sanitised to same-origin, single-slash paths only
  (`lib/redirect.ts` - open-redirect guard, unit-tested against `//host`,
  `javascript:`, backslash and absolute-URL tricks).
- Sharing uses `navigator.share` when the platform offers it (mobile), clipboard copy
  otherwise (`lib/share.ts`), wired to the in-call "Add people" control.

**Consequences.** LAUNCH_PLAN loses every Gmail/SMTP row (budget, accounts, checklist,
risks). Link sharing is bounded by existing join rate limits, the optional password, and
the waiting room - forwarded links alone cannot impersonate anyone. A future password
reset (audit finding H5) will need a delivery channel; when built it brings its own
decision (transactional provider, e.g. Resend free tier) rather than reviving G3.


## D26 - Launch hosting: split free PaaS, no card, no laptop

**Context.** The original plan (Oracle Always Free VM + Cloudflare R2) requires a payment
method on file: Oracle accepts only credit cards and debit "that function like credit"
(virtual, prepaid and single-use rejected), and R2's free tier asks for a card too. The
deployer is a student with no card who explicitly does not want their laptop acting as a
server. The GitHub Student Developer Pack was checked (Sept/Oct 2026 partner list): it no
longer contains any VPS (DigitalOcean left the pack 31 Jul 2026) and its Heroku credit
requires a card; its one card-free compute offer, Azure for Students, was declined in
favour of the pack-free PaaS route. Verified 2026 terms: Render free = 750 shared
instance-hours/month, spins down after 15 min without inbound HTTP *or* WS traffic, and
intercepts /robots.txt while asleep; LiveKit Cloud Build = no card, 5,000 WebRTC
participant-minutes/month as a hard cap with no overage billing.

**Decision.** Launch on a split free-PaaS stack, every provider card-free:
- **Vercel Hobby** serves the Next.js frontend and - via a server-side rewrite of
  `/api/v1/*` to the Render service (`next.config.ts`, target = `API_INTERNAL_URL`) -
  makes the whole app single-origin in the browser, so the existing SameSite=Lax cookie
  auth keeps working with no CORS/CSRF rework.
- **Render Free** runs the single backend web service (existing Dockerfile).
  `NEXT_PUBLIC_WS_URL` points WebSockets straight at Render (token auth, no cookie).
  UptimeRobot pings `/api/health` every 5 minutes - the keep-alive that fits the 750-hour
  budget (one always-on service = 720-744 h) and never touches the /robots.txt trap.
- **Supabase** (Postgres, IPv4 session pooler, sslmode=require) and **Upstash** (Redis for
  rate limiting, which fails open by documented design) replace managed/self-hosted data
  services; the health check runs a trivial SELECT 1 so Supabase never hits its
  inactivity pause.
- **LiveKit Cloud Build** (free, no card) replaces self-hosted LiveKit; **Backblaze B2**
  (free, no card) replaces R2 for evidence - extending D24's ObjectStorage abstraction
  with a configurable S3 endpoint/region (path-style) is a planned repo change.
- **UptimeRobot Free** replaces the Uptime Kuma container (there is no server to run it
  on) and doubles as the keep-alive. DuckDNS remains as an optional custom-domain step.
- No VM, no Caddy, no ufw, no self-hosted media at launch. The Oracle/VM runbook is
  parked (DEPLOYMENT.md + git history) as the upgrade path for when a bank card exists;
  moving to it is an env-swap only (storage provider, LIVEKIT_URL, domain).

**Consequences.** $0/month with no payment method anywhere; Vercel/Render free tiers are
non-commercial (acceptable for testing/portfolio, must upgrade before charging users);
hard caps are dashboarded weekly (Render hours, LiveKit minutes, B2 usage) and fail
cleanly rather than billing. Evidence uploads and reads now flow through Render's
ephemeral filesystem only as a passthrough (objects live in B2). Dev/test still run
locally on Docker Compose with MinIO unchanged - D24's provider split is exactly what
makes the prod switch a configuration change.
