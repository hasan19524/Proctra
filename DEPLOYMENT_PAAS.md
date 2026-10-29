# Proctra — Free-PaaS Deployment Runbook (chosen path, D26)

Companion to [LAUNCH_PLAN.md](LAUNCH_PLAN.md). The old VM/Caddy runbook stays in
[DEPLOYMENT.md](DEPLOYMENT.md) (parked upgrade path for when a card exists).

## 0. How traffic flows

```
Browser ── UI ──────────────► Vercel (Next.js frontend)
Browser ── /api/v1/* ───────► Vercel rewrite ──► Render (FastAPI backend)   ← one origin,
Browser ── WebSocket ───────► Render direct (wss://…, token auth — no cookie)   cookies stay Lax
Browser ── audio/video ─────► LiveKit Cloud (UDP, closest edge to viewer)
Render ──► Supabase (Postgres) · Upstash (Redis) · Backblaze B2 (evidence files)
UptimeRobot ── GET /api/health every 5 min ──► Render   ← keep-alive + Supabase activity
GitHub master ──► Vercel & Render auto-rebuild (CI is the merge gate)
```

## 1. What to handle FIRST — two lists

**A. Accounts now (no card, ~25 min, any order).** Save every value into a local,
gitignored `.env.paaS` (copy `.env.paaS.example`):

| # | Account | What you save from it |
|---|---|---|
| 1 | **Render** (GitHub login) | your account; service comes on deploy day (needs the repo) |
| 2 | **Supabase** | project password + **session-pooler** connection string |
| 3 | **Upstash** (GitHub) | Redis **protocol** URL (`rediss://…`) |
| 4 | **LiveKit Cloud** (GitHub/Google, Build plan = no card) | Project URL + API key + API secret |
| 5 | **Backblaze B2** | bucket `procto-evidence` (private) + application key ID + application key |
| 6 | **Vercel** (GitHub) | —; repo import comes on deploy day |
| 7 | **UptimeRobot** | —; monitor URL comes after the backend is live |

**Region rule:** choose one region family and keep it together —
**Render (Oregon or Ohio) + Supabase US West/East + Upstash same region**. Render free has
no Asia region; keeping DB/Redis next to the backend beats keeping them next to you
(REST latency from BD ≈ 200–250 ms either way; video never touches this path — LiveKit
picks the edge nearest each viewer).

**B. Deploy day wiring order** (strict dependencies — later steps consume earlier URLs):

1. **Repo prep merged** (§3, all pending items green in the gate).
2. **Render service created** — root `backend/`, Docker, region per above, health path
   `/api/health`, pre-deploy command `alembic upgrade head`, **all Render env vars from
   §2.2 filled** → first deploy → record the service URL
   `https://<name>-<region>.onrender.com`.
3. **Vercel import** — root directory `frontend/`, add its two env vars (they reference
   the URL from step 2) → deploy → open the site and register/login (proves the proxy +
   cookie flow end to end).
4. **UptimeRobot monitor** → `https://<name>.onrender.com/api/health`, every 5 min
   (never `/robots.txt` — Render answers that path itself while asleep).
5. Smoke tests: LAUNCH_PLAN §3.4 checklist (B2 upload test lands with its code change).
6. Optional polish: DuckDNS CNAME → Vercel (custom domain), same for Render.

## 2. Env variables — exactly what goes where

### 2.1 Vercel (frontend) — 2 variables, scope "Build & Runtime"

| Variable | Value | Why |
|---|---|---|
| `API_INTERNAL_URL` | `https://<render-name>.onrender.com` | `next.config.ts` rewrites `/api/v1/:path*` to this — the same-origin proxy that keeps SameSite=Lax cookies working (no CORS work by design) |
| `NEXT_PUBLIC_WS_URL` | `wss://<render-name>.onrender.com` | WebSocket connects **direct** to Render (inlined at build; no trailing slash; token auth, never a cookie) |

Project settings (not env): Root Directory = `frontend`, framework auto-detected
(Next.js). No `vercel.json` needed — the rewrite already lives in `next.config.ts`.

### 2.2 Render (backend) — its env dashboard

**Required:**

| Variable | Value / source |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` (boot refuses production otherwise) |
| `SECRET_KEY` | 64 random chars (`python -c "import secrets;print(secrets.token_urlsafe(64))"`) — boot refuses the dev default |
| `DATABASE_URL` | `postgresql+asyncpg://postgres.<project-ref>:<db-password>@<pooler-host>.supabase.com:5432/postgres?sslmode=require` ← Supabase **session** pooler (IPv4), never the transaction pooler (asyncpg uses prepared statements) |
| `REDIS_URL` | `rediss://default:<password>@<db>-<region>.upstash.io:6379` ← Upstash Redis **protocol** URL |
| `LIVEKIT_URL` | `wss://<project>.livekit.cloud` (server-side) |
| `LIVEKIT_PUBLIC_URL` | `wss://<project>.livekit.cloud` (browser-facing, handed to clients by the token endpoint) |
| `LIVEKIT_API_KEY` | LiveKit Cloud dashboard |
| `LIVEKIT_API_SECRET` | LiveKit Cloud dashboard |
| `FRONTEND_URL` | `https://<vercel-domain>` — one half of the WS origin allow-list |
| `BACKEND_CORS_ORIGINS` | `https://<vercel-domain>` (comma list or JSON array both parse) — other half of the WS origin allow-list |

**Recommended hardening:**

| Variable | Value |
|---|---|
| `TRUSTED_HOSTS` | `<vercel-domain>,<render-domain>` (comma/JSON; **empty = no Host check at all** — behind the Vercel proxy verify which Host header arrives, then pin both) |

**Storage block — planned names, ships with the B2 code change (LAUNCH_PLAN §3.2):**

| Variable | Value |
|---|---|
| `STORAGE_PROVIDER` | `b2` (today only `minio\|r2` exists — the endpoint generalization is the pending repo change) |
| `B2_ENDPOINT` | `https://s3.<region>.backblazeb2.com` (from the bucket page) |
| `B2_REGION` | e.g. `us-west-002` |
| `B2_ACCESS_KEY_ID` / `B2_SECRET_ACCESS_KEY` | the application key you created |
| `B2_BUCKET` | `procto-evidence` |

**Optional (defaults are fine):** `ACCESS_TOKEN_TTL_MINUTES=15`,
`REFRESH_TOKEN_TTL_DAYS=30`, `STORAGE_RETENTION_DAYS=90`,
`STORAGE_SIGNED_URL_TTL_SECONDS=300`, `STORAGE_CLEANUP_INTERVAL_HOURS=6`.
Leave `COOKIE_SECURE` unset — it auto-enables in production.

**Platform-side (Render dashboard / blueprint):** health check path `/api/health`;
pre-deploy command `alembic upgrade head`; Docker runtime port — ⚠️ Render injects
`$PORT` and the current Dockerfile hardcodes 8001 (repo prep §3).

### 2.3 Supabase — no variables of its own; it *produces* three values

1. **DB password** (set at project creation) and the **Session pooler** connection
   string → becomes Render's `DATABASE_URL` (user format `postgres.<project-ref>`,
   port 5432, `sslmode=require`).
2. Region chosen per §1A. Nothing else of ours runs here — files go to B2, auth is our
   own (no Supabase Auth).

### 2.4 Upstash — produces one value

Region = same as Render. Dashboard → your DB → **Redis protocol** URL → Render's
`REDIS_URL`. (Used for rate limiting only; the limiter fails open if the quota —
10k cmds/day — is exhausted: degradation, not outage.)

### 2.5 LiveKit Cloud — produces four values

Project Settings → **Project URL** → `LIVEKIT_URL` *and* `LIVEKIT_PUBLIC_URL`;
**API Key/Secret** → `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`. Frontend needs none (the
token endpoint returns the URL). Watch the dashboard: Build plan = **5,000 WebRTC
participant-min/mo hard cap**, 100 concurrent, 50 GB egress — hard stop, never a bill.

### 2.6 Backblaze B2 — produces five values

Bucket (private, region visible on the bucket page) + application key scoped to that
bucket → the planned `B2_*` block above. No card on the account. Fail-clearly behaviour
already handles a full bucket; watch the 10 GB.

### 2.7 UptimeRobot — no variables

Monitor URL `https://<render-name>.onrender.com/api/health`, interval **5 min**
(Render sleeps at 15 min of silence; WS traffic also counts since Feb 2026, so meetings
self-sustain and the pinger only covers idle gaps). Alert contact = webhook
(Telegram/Discord) or email.

### 2.8 GitHub Actions — nothing to paste

CI runs its own Postgres/Redis/MinIO services in the runner; Vercel and Render deploy
via their own Git integrations (OAuth, not secrets).

## 3. Repo prep before deploy day (merge-ready, all gated)

- [ ] Dockerfile CMD honors `--port ${PORT:-8001}` (Render injects `$PORT`).
- [ ] `render.yaml` blueprint: web service (root `backend/`), the env table §2.2 as
      `envVars`, health path, `preDeploy: alembic upgrade head`.
- [ ] B2 endpoint/region generalization of the D24 storage abstraction (provider preset
      + fail-fast validation, tests against MinIO unchanged).
- [ ] Audit H1 (password/token out of WS URLs) lands first — do not deploy with secrets
      in query strings.
- [ ] `./scripts/procto.ps1 check` green.

## 4. Honest free-tier watch list (dashboards, weekly)

| Dashboard | Threshold | Meaning |
|---|---|---|
| Render instance hours | 750/mo, one service ≈ 744 | never add a second free service |
| LiveKit usage | 5,000 participant-min | fails cleanly mid-month at cap |
| B2 usage | 10 GB | uploads fail-clearly |
| Upstash commands | 10k/day | rate limiting degrades open |
| Supabase | inactivity pause | health `SELECT 1` prevents it |

Upgrade triggers: first paying customer → Vercel/Render paid (or card → Oracle path,
pure env swap); sustained exams → LiveKit Ship.
