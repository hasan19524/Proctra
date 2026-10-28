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
| `LIVEKIT_PUBLIC_URL` | browser-reachable SFU URL, e.g. `wss://procto.example.com` — inside the compose network the backend hands browsers `LIVEKIT_URL` (`ws://livekit:7880`), which they cannot resolve, so this must be the public endpoint (see *LiveKit* below) |
| `BACKEND_CORS_ORIGINS` | JSON list of your frontend origin(s), e.g. `["https://procto.example.com"]` |
| `FRONTEND_URL` | `https://procto.example.com` |
| `TRUSTED_HOSTS` | comma list of hostnames, e.g. `procto.example.com` |
| `COOKIE_SECURE` | `true` |
| `STORAGE_PROVIDER` | `r2` — the backend refuses to boot in production with `minio` |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | Cloudflare R2 credentials and private bucket (see *Object storage* below) |
| `STORAGE_RETENTION_DAYS` | evidence retention (default `90`; `0` = keep forever) |
| `NEXT_PUBLIC_API_URL` | leave empty (frontend proxies `/api` internally) |
| `NEXT_PUBLIC_WS_URL` | `wss://procto.example.com` |
| `DOMAIN` | `procto.example.com` (used by Caddy) |

The backend refuses to boot in production with dev secrets or `APP_DEBUG=true`
(see `app/core/config.py`).

## 2. LiveKit configuration

Edit `livekit/livekit.yaml` and set `keys:` to match `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`.
Also configure `rtc.port_range` and the public IP for WebRTC (see LiveKit docs).

The URL split:

- **`LIVEKIT_URL`** — inside the compose network the backend talks to the SFU at
  `ws://livekit:7880` (server-side room admin, token minting). The compose file
  sets this for you; do not expose it publicly.
- **`LIVEKIT_PUBLIC_URL`** — what browsers actually connect to. Browsers cannot
  resolve the Docker service name `livekit`, so leaving this unset in production
  makes every call join fail. Point it at a reachable endpoint: either front
  LiveKit with Caddy on the same domain (add a `/rtc` + WebSocket route) or
  expose the LiveKit ports on the host/edge and use `ws(s)://<host>:7880`.

WebRTC media also needs UDP. If you set `rtc.port_range` in `livekit.yaml`, that
whole range must be reachable by clients (published at the host or load
balancer); otherwise audio/video falls back to TCP relay or fails outright.

## 3. Build and start

Everything comes from one env file. Either edit `.env` in place (§1), or keep
`.env.prod` separately — it must name itself (`COMPOSE_ENV_FILE=.env.prod` as
its last line) so the services load the same file the flags substitute from:

```bash
# Edit .env in place:
docker compose -f docker-compose.prod.yml up -d --build

# Or use a separate .env.prod (add `COMPOSE_ENV_FILE=.env.prod` to it):
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

> Do not rely on a `COMPOSE_ENV_FILE` **shell** variable: Compose uses
> `--env-file` (or the default `.env`) for `${VAR}` substitution, so a shell
> variable alone lets `R2_*`, `SECRET_KEY`, and friends silently fall back to
> the dev `.env`.

This starts Postgres, Redis, LiveKit, runs Alembic migrations (`migrate` service),
then starts the backend, frontend, and Caddy. The backend refuses to start if
secrets are dev defaults, `APP_DEBUG=true`, or R2 storage is unconfigured — by
design; fix the reported variables and re-run `up -d`.

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

## Object storage: Cloudflare R2 (evidence, screenshots)

Production stores evidence in a **private** Cloudflare R2 bucket (DECISIONS.md D24);
local development uses MinIO from `docker-compose.yml`. `STORAGE_PROVIDER` selects
the provider and the backend **fails at startup** with a precise message if R2 is
configured incompletely.

Before the first production deployment:

1. Create a private R2 bucket (e.g. `procto-evidence`) in the Cloudflare dashboard.
2. Create an R2 API token scoped to that bucket (object read/write only) and put the
   account id + token id/secret into `.env` as `R2_*` — server-side only, never in
   Git and never exposed to the frontend.
3. Start the stack; the first upload verifies connectivity end-to-end. Confirm the
   bucket denies anonymous access and that signed URLs stay short-lived
   (`STORAGE_SIGNED_URL_TTL_SECONDS`, default 300 s).
4. Exercise upload, download (including Range reads), signed URL, and deletion
   through the app against R2 before relying on it.
5. Configure storage monitoring/usage alerts in Cloudflare (growth, error rate).
6. Confirm `STORAGE_RETENTION_DAYS` matches policy (default 90 days; `0` = keep
   forever). The backend sweeps expired files on that schedule and never removes
   files under legal hold.
7. Include the bucket in backup/replication alongside Postgres backups and verify
   recovery (`aws s3 sync` works from both ends).
8. Verify no development configuration leaked: `.env` must contain no `MINIO_*`
   endpoints or `minioadmin` credentials, and the bucket must not be public.

Switching providers later is an object migration (`aws s3 sync`), not a code
change — the database stores object keys, never provider URLs.

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
- [ ] `STORAGE_PROVIDER=r2` with all four `R2_*` values set; R2 bucket is private and API-token-scoped.
- [ ] No `MINIO_*` dev endpoints or `minioadmin` credentials in production env files.

## CI

GitHub Actions runs backend (ruff, mypy, pytest) and frontend (eslint, vitest, build)
on every push/PR. See `.github/workflows/ci.yml`.