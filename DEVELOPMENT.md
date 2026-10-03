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

Windows (PowerShell):

```powershell
./scripts/procto.ps1 setup      # deps + .env + migrations
./scripts/procto.ps1 infra up   # postgres + redis + livekit
./scripts/procto.ps1 dev        # backend :8001 + frontend :3001
```

Linux / macOS (Make):

```bash
cp .env.example .env      # fill in secrets (LiveKit keys are generated for you)
make infra-up             # start postgres + redis + livekit
make setup                # backend deps + frontend deps + db migration
make dev                  # backend :8001 + frontend :3001
```

## Commands

Both runners expose the same verbs: `setup`, `dev`, `dev-backend`, `dev-frontend`,
`check`, `test`, `lint`, `typecheck`, `fmt`, `infra up|down`, `db upgrade|revision`.
Windows: `./scripts/procto.ps1 <verb>` · elsewhere: `make <target>`.

| Command (Make) | PowerShell | What it does |
|---|---|---|
| `make dev` | `procto.ps1 dev` | run backend (uvicorn --reload) and frontend (next dev) |
| `make dev-backend` / `dev-frontend` | same verb | run one side only |
| `make dev-full` | — | everything (incl. apps) in Docker |
| `make infra-up` / `infra-down` | `procto.ps1 infra up\|down` | start/stop infrastructure containers |
| `make db-upgrade` | `procto.ps1 db upgrade` | apply Alembic migrations |
| `make db-revision m="msg"` | `procto.ps1 db revision "msg"` | create a new migration |
| `make test` | `procto.ps1 test` | backend pytest + frontend vitest |
| `make lint` | `procto.ps1 lint` | ruff + eslint/prettier check |
| `make typecheck` | `procto.ps1 typecheck` | mypy + tsc --noEmit |
| `make check` | `procto.ps1 check` | lint + typecheck + tests |
| `make fmt` | `procto.ps1 fmt` | auto-fix formatting on both sides |

## Ports

| Port | Service |
|---|---|
| 3001 | Next.js dev |
| 8001 | FastAPI |
| 5434 | PostgreSQL (host port; container 5432) |
| 6380 | Redis (host port; container 6379) |
| 7880 / 7881 | LiveKit HTTP + RTC (UDP 50000-50099 in compose) |

Ports are offset from the usual 3000/8000/5432/6379 to coexist with other projects
on this machine — see [DECISIONS.md](./DECISIONS.md) D10.

## Testing strategy

| Layer | Tool | When |
|---|---|---|
| Backend unit/service | `pytest` + `pytest-asyncio` | every phase |
| Backend API | `httpx.AsyncClient` against the FastAPI app | every phase with endpoints |
| Backend WS | FastAPI `TestClient` websocket support | realtime phases |
| Frontend unit | `vitest` + React Testing Library | component logic |
| Frontend type | `tsc --noEmit` | every phase |
| E2E / multi-browser | Playwright | Phase 15 (full E2E validation) |

Rule from the spec: every phase runs `check` (see `scripts/procto.ps1`) before it is considered done.

## Phase status

Owner directive (2026-10-03): develop autonomously through Phase 15 — no
phase-by-phase approvals. AI/ML/proctoring/exam-intelligence stays outside the
boundary.

| Phase | Status |
|---|---|
| 0 — Architecture & foundation | ✅ done |
| 1 — Design system + Meet-style UI | ✅ done |
| 2 — Authentication + user system | ✅ done |
| 3 — Meeting creation, join, pre-join lobby | ✅ done |
| 4 — Real-time WS core (FastAPI + Redis + PG) | ✅ done |
| 5 — Chat | ⬜ |
| 6 — Participant management + host controls | ⬜ |
| 7 — Notes | ⬜ |
| 8 — Reactions + hand raise (real) | ⬜ |
| 9 — LiveKit real audio/video | ⬜ |
| 10 — Screen sharing | ⬜ |
| 11 — Complete meeting experience | ⬜ |
| 12 — Failure + reconnection | ⬜ |
| 13 — Security hardening | ⬜ |
| 14 — History + polish | ⬜ |
| 15 — Full E2E validation | ⬜ |

## Conventions

- Commit style: `feat(auth): ...`, `chore(repo): ...`, `docs(arch): ...`.
- One logical change per commit; no enormous mixed commits.
- No giant files — split routers / services / schemas / handlers by domain.
- No features outside the specification without asking the project owner first.
- No AI/ML implementation — UI placeholders only, and only when a phase asks for them.
- Keep this documentation set in sync with the code.
