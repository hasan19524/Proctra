# Procto

**Procto** is a real-time video meeting platform. The core product is a polished, modern
meeting experience; Exam/Interview mode is a specialized mode built **on top of** the same
Meeting Core — not a separate implementation. Exam mode adds **AI proctoring**: a
self-hosted vision model classifies integrity signals (looking away, no face, multiple
faces, eyes closed, speaking, tab hidden) locally in the browser; the server scores and
stores them, and the host gets a live integrity feed plus a downloadable report.

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

In Exam/Interview mode, proctoring runs on top of Meeting Core: a self-hosted MediaPipe
model classifies integrity signals **in the browser** (video never leaves the device), the
server scores and persists them, and the host gets a live flag feed plus a report
(`GET /meetings/{code}/report` + CSV).

Future layers (**not part of the current implementation**): AI Meeting Assistant.

## Status

Phase 0 — Architecture & project foundation.

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the phase checklist.
See [DEPLOYMENT.md](./DEPLOYMENT.md) for production deployment.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| Cache / bus | Redis 7 |
| Realtime (app) | WebSockets (FastAPI) |
| Realtime (media) | WebRTC via **LiveKit** SFU |
| Object storage | **MinIO** (dev/test) → **Cloudflare R2** (prod), one S3 abstraction (DECISIONS.md D24) |
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

Prerequisites: Docker (+ Compose), Node 20+, Python 3.13+, `uv`.
Task runner: **PowerShell script** on Windows (`scripts/procto.ps1`), **Make** elsewhere.

```powershell
# Windows (PowerShell)
./scripts/procto.ps1 setup     # deps + .env + migrations
./scripts/procto.ps1 infra up  # postgres + redis + livekit + minio in Docker
./scripts/procto.ps1 dev       # backend :8001 + frontend :3001 (2 windows)
./scripts/procto.ps1 check     # lint + typecheck + tests
```

```bash
# Linux / macOS (Make)
cp .env.example .env
make setup && make infra-up && make dev
make check
```

- Frontend: http://localhost:3001
- Backend API: http://localhost:8001/api/health (docs: `/api/docs`)
- LiveKit: http://localhost:7880 (dev key pair in `.env`)
- MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`)

## License

Private / unlicensed — project under development.
