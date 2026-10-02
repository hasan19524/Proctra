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
