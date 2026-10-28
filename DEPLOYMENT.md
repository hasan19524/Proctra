# Deployment Guide — Procto

This document describes how to deploy Procto to a production environment.

## Prerequisites

- A Linux VM (Ubuntu 22.04+ recommended) with Docker + Docker Compose v2.
- A domain name pointed at the VM (A record).
- Ports 80 and 443 open to the internet (Caddy provisions TLS automatically).
- (Optional) A managed Postgres/Redis if you prefer not to self-host them.

## 1. Clone and configure

```bash
git clone <your-repo-url> procto
cd procto
cp .env.example .env
```

Edit `.env` and set **production values**:

| Variable | Notes |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` — min 32 chars |
| `JWT_ALGORITHM` | `HS256` (default) |
| `POSTGRES_PASSWORD` | strong password |
| `REDIS_PASSWORD` | strong password (or leave empty to disable auth) |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | must match `livekit/livekit.yaml` `keys:` |
| `BACKEND_CORS_ORIGINS` | JSON list of your frontend origin(s), e.g. `["https://procto.example.com"]` |
| `FRONTEND_URL` | `https://procto.example.com` |
| `TRUSTED_HOSTS` | comma list of hostnames, e.g. `procto.example.com` |
| `COOKIE_SECURE` | `true` |
| `NEXT_PUBLIC_API_URL` | leave empty (frontend proxies `/api` internally) |
| `NEXT_PUBLIC_WS_URL` | `wss://procto.example.com` |
| `DOMAIN` | `procto.example.com` (used by Caddy) |

The backend refuses to boot in production with dev secrets or `APP_DEBUG=true`
(see `app/core/config.py`).

## 2. LiveKit configuration

Edit `livekit/livekit.yaml` and set `keys:` to match `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`.
Also configure `rtc.port_range` and the public IP for WebRTC (see LiveKit docs).

## 3. Build and start

```bash
make prod-up
# or:
docker compose -f docker-compose.prod.yml up -d --build
```

This starts Postgres, Redis, LiveKit, runs Alembic migrations (`migrate` service),
then starts the backend, frontend, and Caddy.

## 4. Verify

```bash
# Health
curl https://procto.example.com/api/health

# Logs
make prod-logs
```

Caddy automatically provisions a Let's Encrypt certificate for `DOMAIN`.

## 5. Updating

```bash
git pull
make prod-up          # rebuilds changed images
make prod-migrate     # if new migrations exist (also runs on backend start)
```

## 6. Backups

Postgres data lives in the `procto-pgdata-prod` Docker volume. Back up with:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U procto procto > backup-$(date +%F).sql
```

## 7. Scaling notes

- The backend is stateful only via Redis pub/sub for cross-worker fan-out; running
  multiple backend replicas is supported (increase `--workers` or replicas).
- LiveKit is the media plane; scale it independently per LiveKit docs.
- The in-memory connection registry is per-process; cross-process delivery uses
  Redis pub/sub (REALTIME.md §1).

## Frontend assets: self-hosted MediaPipe

Exam-mode proctoring ships ~44 MB of static assets inside the frontend image under
`public/`:

- `public/models/face_landmarker.task` (~3.6 MB) — the MediaPipe face landmarker model.
- `public/mediapipe-wasm/` — vision WASM in module and nosimd variants.

They are served by the frontend itself — no CDN and no API keys at runtime. The engine
probes the browser once and downloads only the WASM variant it needs, so a single visitor
pulls a small fraction of the total. Ensure the edge proxy serves `.wasm` with
`Content-Type: application/wasm` (Caddy does this by default).

## Edge proxy: camera / microphone permissions

Caddy sets `Permissions-Policy: camera=(self), microphone=(self)`. Keep the equivalent on
any edge proxy: a policy of `camera=(), microphone=()` denies `getUserMedia` site-wide and
breaks every meeting, not just proctoring. Both the prejoin camera check and the
proctoring engine require the origin to be allowed.

## Security checklist before going live

- [ ] `SECRET_KEY` is 32+ chars and unique.
- [ ] `POSTGRES_PASSWORD`, `REDIS_PASSWORD` are strong and not the defaults.
- [ ] `LIVEKIT_API_SECRET` matches `livekit/livekit.yaml`.
- [ ] `APP_DEBUG=false`, `APP_ENV=production`.
- [ ] `BACKEND_CORS_ORIGINS` lists only your real origins (no `*`).
- [ ] `TRUSTED_HOSTS` set to your domain.
- [ ] `COOKIE_SECURE=true`.
- [ ] HTTPS is enforced (Caddy does this; verify the cert).
- [ ] Database is not exposed on a public port (compose only exposes 80/443).
- [ ] Edge proxy allows camera/microphone on the origin (`Permissions-Policy: camera=(self), microphone=(self)`).
- [ ] `.wasm` is served with `Content-Type: application/wasm` (MediaPipe proctoring assets).

## CI

GitHub Actions runs backend (ruff, mypy, pytest) and frontend (eslint, vitest, build)
on every push/PR. See `.github/workflows/ci.yml`.