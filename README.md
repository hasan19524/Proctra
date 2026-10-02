# Procto

**Procto** is a real-time video meeting platform. The core product is a polished, modern
meeting experience; Exam/Interview mode is a specialized mode built **on top of** the same
Meeting Core — not a separate implementation.

```text
                         PROCTO
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     CREATE MEET       JOIN MEET      EXAM/INTERVIEW
          │                                 │
          └────────────────┬────────────────┘
                           │
                     MEETING CORE
                           │
       ┌───────────┬───────┼───────┬───────────┐
       │           │       │       │           │
     Video       Audio    Chat   Screen      Notes
       │                   Share
       ├── Participants
       ├── Reactions
       ├── Raise Hand
       ├── Host Controls
       ├── Security (password, waiting room, lock)
       ├── Reconnection
       └── Meeting History
```

Future layers (**not part of the current implementation**): AI Meeting Assistant,
ML Proctoring Engine.

## Status

Phase 0 — Architecture & project foundation.

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the phase checklist.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| Cache / bus | Redis 7 |
| Realtime (app) | WebSockets (FastAPI) |
| Realtime (media) | WebRTC via **LiveKit** SFU |
| Infra | Docker Compose (infra only), Make, Git |

## Documentation

| File | Contents |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design, frontend/backend/realtime/media/deployment |
| [DATABASE.md](./DATABASE.md) | Schema, conventions, migrations |
| [REALTIME.md](./REALTIME.md) | WebSocket protocol + LiveKit split |
| [SECURITY.md](./SECURITY.md) | Auth, authorization, hardening |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Setup, commands, testing, phase status |
| [DECISIONS.md](./DECISIONS.md) | Decision records (why LiveKit, monorepo, ...) |

## Quick start

Prerequisites: Docker (+ Compose), Node 20+, Python 3.13+, `uv`, Make.

```bash
cp .env.example .env          # then edit secrets
make infra-up                 # postgres + redis + livekit in Docker
make setup                    # install backend + frontend deps, run migrations
make dev                      # backend (8000) + frontend (3000)
make check                    # lint + typecheck + tests
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/health
- LiveKit: http://localhost:7880 (dev key pair in `.env`)

## License

Private / unlicensed — project under development.
