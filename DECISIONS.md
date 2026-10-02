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

## D10 � Local port allocation (coexistence with other projects)

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
