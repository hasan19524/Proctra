# Procto — Development Guide

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker + Compose | recent | infrastructure (postgres, redis, livekit) |
| Node.js | 20+ | frontend |
| Python | 3.13+ | backend |
| uv | latest | Python env + dependency management |
| Make | any | task entry points |

## Repository layout

```text
PROCTO/
├── README.md ARCHITECTURE.md DATABASE.md REALTIME.md SECURITY.md
├── DEVELOPMENT.md DECISIONS.md        # this file, decision records
├── .env.example                        # copy to .env
├── docker-compose.yml                  # infra only
├── Makefile                            # dev/test/lint entry points
├── docs/phases/                        # per-phase implementation notes
├── frontend/                           # Next.js app
│   └── src/{app,components,lib,hooks,stores,types}
└── backend/                            # FastAPI app
    ├── app/{main,core,api,ws,models,schemas,services,db}
    ├── alembic/
    └── tests/
```

## Setup

```bash
cp .env.example .env      # fill in secrets (LiveKit keys are generated for you)
make infra-up             # start postgres + redis + livekit
make setup                # backend deps + frontend deps + db migration
make dev                  # backend :8000 + frontend :3000
```

## Commands

| Command | What it does |
|---|---|
| `make dev` | run backend (uvicorn --reload) and frontend (next dev) together |
| `make dev-backend` / `make dev-frontend` | run one side only |
| `make dev-full` | everything (incl. apps) in Docker |
| `make infra-up` / `make infra-down` | start/stop infrastructure containers |
| `make db-upgrade` | apply Alembic migrations |
| `make db-revision m="msg"` | create a new empty migration |
| `make test` | backend pytest + frontend vitest |
| `make lint` | ruff (backend) + eslint/prettier check (frontend) |
| `make typecheck` | mypy (backend) + tsc --noEmit (frontend) |
| `make check` | lint + typecheck + tests |
| `make fmt` | auto-fix formatting on both sides |

## Ports

| Port | Service |
|---|---|
| 3000 | Next.js dev |
| 8000 | FastAPI |
| 5432 | PostgreSQL |
| 6379 | Redis |
| 7880 / 7881 | LiveKit HTTP + RTC (UDP 50000-60000 in compose) |

## Testing strategy

| Layer | Tool | When |
|---|---|---|
| Backend unit/service | `pytest` + `pytest-asyncio` | every phase |
| Backend API | `httpx.AsyncClient` against the FastAPI app | every phase with endpoints |
| Backend WS | FastAPI `TestClient` websocket support | realtime phases |
| Frontend unit | `vitest` + React Testing Library | component logic |
| Frontend type | `tsc --noEmit` | every phase |
| E2E / multi-browser | Playwright | Phase 18 (testing & polish) |

Rule from the spec: every phase runs `make check` before it is considered done.

## Phase status

| Phase | Status |
|---|---|
| 0 — Architecture & foundation | ✅ done |
| 1 — Design system | ⬜ not started |
| 2 — Authentication | ⬜ |
| 3 — Procto Home | ⬜ |
| 4 — Create meeting | ⬜ |
| 5 — Join + pre-join lobby | ⬜ |
| 6 — Real-time meeting core | ⬜ |
| 7 — Complete meeting room | ⬜ |
| 8 — Participant management | ⬜ |
| 9 — Chat / messages | ⬜ |
| 10 — Reactions + hand raise | ⬜ |
| 11 — Screen sharing | ⬜ |
| 12 — Notes / writing | ⬜ |
| 13 — Meeting security | ⬜ |
| 14 — Failure & reconnection | ⬜ |
| 15 — Meeting history | ⬜ |
| 16 — Future AI UI only | ⬜ |
| 17 — Exam/Interview foundation | ⬜ |
| 18 — Testing & polish | ⬜ |

## Conventions

- Commit style: `feat(auth): ...`, `chore(repo): ...`, `docs(arch): ...`.
- One logical change per commit; no enormous mixed commits.
- No giant files — split routers / services / schemas / handlers by domain.
- No features outside the specification without asking the project owner first.
- No AI/ML implementation — UI placeholders only, and only when a phase asks for them.
- Keep this documentation set in sync with the code.
