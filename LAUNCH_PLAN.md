# Proctra — Zero-Cost Launch Plan

**Goal:** production deployment with **$0/month** and every feature working.

Decisions (confirmed):

- **Hosting** — **split free PaaS, no card, no laptop** (D26): Vercel (frontend) +
  Render free (backend) + Supabase (Postgres) + Upstash (Redis) + LiveKit Cloud free
  (video) + Backblaze B2 (evidence) + UptimeRobot (keep-alive & alerts).
- **Scope** — build the full product backlog **before** going live (phases below).
- **Domain** — DuckDNS `proctrahasan19524.duckdns.org` ✅ created (token in gitignored
  `.env.duckdns`); used later as a custom domain on Vercel — deployment works first on
  the free `*.vercel.app` / `*.onrender.com` names.

Related docs: [DEPLOYMENT.md](DEPLOYMENT.md) (VM/R2 runbook — parked, see §3.1),
[DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md),
[AUDIT.md](AUDIT.md).

---

## 0. The $0 budget (all no-card signups)

| Need | Provider / plan | Cost | Card? | Limit we design around |
|---|---|---|---|---|
| Frontend | **Vercel Hobby** | $0 | No | 100 GB bw/mo; free tier is **non-commercial** (portfolio/testing now, upgrade before charging users) |
| Backend | **Render Free web service** (one only) | $0 | No | **750 instance-h/mo shared per workspace** — one always-on service = 720–744 h ✅ fits; ≥6 h margin, see §0.5 |
| Database | **Supabase Free** (Postgres) | $0 | No | 500 MB; pauses on ~7 days inactivity → our health check runs `SELECT 1` every 5 min (keeps it live) |
| Redis (rate limits) | **Upstash Free** | $0 | No | 10k cmds/day; our limiter **fails open** (documented) if exhausted — watch, don't panic |
| Video | **LiveKit Cloud Build** | $0 | No | **5,000 WebRTC participant-min/mo hard cap**, 100 concurrent, 50 GB egress; no overage billing (hard stop, resets 1st) |
| Evidence storage | **Backblaze B2** (10 GB) | $0 | No | uploads fail-clearly when full; ✅ generic `s3` provider shipped (§3.2) |
| Keep-alive + uptime | **UptimeRobot Free** | $0 | No | 50 monitors @ 5-min → pings `/api/health` (never `robots.txt`) + alerts via webhook/email |
| CI | GitHub Actions (public repo) | $0 | No | unlimited minutes + free arm64 runners |
| Domain (optional polish) | DuckDNS ✅ | $0 | No | CNAME → Vercel/Render when we want the branded URL |

**One-time: $0. Monthly: $0.** Deliberately avoided: anything wanting a card (Oracle, R2,
Heroku credit), self-hosting on the laptop (user decision), shady "free VPS" ad-hosts
(no SLA — never for exam data).

---

### 0.5 How the split stack is engineered (the two tricks)

1. **One origin via Vercel rewrites.** The browser only ever talks to the Vercel domain:
   the existing Next.js rewrite (`next.config.ts`, target set through the
   `API_INTERNAL_URL` env) proxies `/api/v1/*` to the Render service, so `Set-Cookie`
   arrives on the frontend's own origin — **SameSite=Lax cookies keep working, zero
   CORS/CSRF rework**. WebSockets skip the proxy:
   `NEXT_PUBLIC_WS_URL=wss://<service>.onrender.com` connects direct (WS auth is the
   token, never a cookie).
2. **Keep-alive that satisfies three platforms at once.** UptimeRobot hits
   `/api/health` every **5 min** (Render sleeps at 15 min of silence — and since Feb 2026
   WS messages also count, so live meetings self-sustain). That same handler runs a
   trivial `SELECT 1`, which keeps Supabase out of its inactivity pause. Never ping
   `/robots.txt` — Render intercepts it while asleep and the ping would do nothing.

**Honest limits of free tier (accepted for launch, all upgradeable later):**

- Render 750 h/mo: one 24/7 service fits (744 h worst case) — **never add a second free
  Render service**; exhaustion suspends services until the month resets.
- LiveKit 5,000 participant-min ≈ e.g. 3 people × ~27 h, or eight 10-student hourly exams
  per month — fine for building/testing/small classes; a hard cap (fails cleanly, never
  bills).
- Vercel/Render free tiers are **non-commercial**: perfect for portfolio + testing now;
  before charging real users, upgrade (Render $7/mo or move to Oracle when a card exists).
- Supabase free uses an **IPv4 session pooler** endpoint with `sslmode=require` (asyncpg
  safe); watch its pause rule via the health-ping above.
- On the VM path later (card): everything ports over — same compose stack, only env
  values change (storage → R2, media → self-hosted LiveKit, no sleep/pings at all).

---

## 1. Phase 1 — Build the backlog (before launch)

Rule for every item: `./scripts/procto.ps1 check` stays green, the item ships with tests,
and CI (incl. Playwright once #8 lands) is green.

| # | Workstream | Done means | Size |
|---|---|---|---|
| 1 | **T1 trust layer** — ⚠️ *pending your approval* of the trust proposal you were reviewing | Heartbeat + SFU cross-checks, report integrity tiers, host "mark observed"; a missing/late clip is reported honestly and never implies cheating | L |
| 2 | **B1 security audit** | Background audit delivered — see [AUDIT.md](AUDIT.md) (H1–H8, M1–M12, L1–L9, no IDOR); fix pass in Top-10 order, SECURITY.md aligned at the end | M |
| 3 | **B4 host controls** | Host can globally disable + per-participant mute/cam/screen-share controls, enforced server-side, audited | M |
| 4 | **Evidence capture UI** (frontend client for the Phase-17 storage API — audit M2) | Clip/screenshot capture during exam, watermark + nonce, upload with retry/offline honesty, thumbnails in host report, owner/host-only access end-to-end | L |
| 5 | **B3 exports** | Word (.docx) + Excel (.xlsx) report exports and per-student PDF dossier; audit-logged (CSV already exists) | M |
| 6 | **B5 DMs + B6 settings page** | Host-enableable DMs between participants (toggle-only first); real settings page (profile, password, preferences) | M + M |
| 7 | **Invite & share polish** ✅ *(shipped, D25)* | Link share/copy (`navigator.share` → clipboard), `?next=` return-to after login/register, open-redirect guard — **no email anywhere** | S |
| 8 | **B2 demo data + G2 Playwright E2E** | Seed script (demo users/meetings/exam/report); Playwright covers register→join→report in CI | S + M |
| 9 | **G4 observability** | UptimeRobot external checks (doubles as keep-alive §0.5) + webhook alerts, structured log review, Docker log rotation for local/prod-VM later | S |

**Phase 1 exit:** every row shipped (or explicitly descoped by you), gate green, E2E green.
If you decline the T1 proposal, start with #2 (audit fixes — already underway).

---

## 2. Phase 2 — Infrastructure (all no-card, ~25 min)

### 2.1 Accounts (manual, in parallel with Phase 1)

1. **Vercel** — sign up with GitHub → import nothing yet (repo connect comes at deploy).
2. **Render** — sign up with GitHub → note: free plan = **one** web service.
3. **Supabase** — new project, region **closest to you** (Singapore/Mumbai) → save the
   **session pooler** connection string + `db password`.
4. **Upstash** — sign up with GitHub → create Redis DB (region same as Render) → save the
   `rediss://` URL.
5. **LiveKit Cloud** — sign up (GitHub/Google) → **Build plan, no card** → create project →
   save Project URL + API key/secret.
6. **Backblaze B2** — enable B2 → create private bucket (e.g. `procto-evidence`) →
   create an application key scoped to it → save key ID/application key + endpoint.
7. **UptimeRobot** — free account → monitor #1: `https://<service>.onrender.com/api/health`
   every 5 min (this is the Render keep-alive **and** the Supabase activity source).

**No Gmail, no Oracle, no Cloudflare** (D25 / D26). Exact values to save and which
dashboard each one feeds: [DEPLOYMENT_PAAS.md](DEPLOYMENT_PAAS.md) §1–2 (fill-in
template: `.env.paaS.example`).

### 2.2 Secrets (Render env + Vercel env)

Render gets: `SECRET_KEY`, `DATABASE_URL` (Supabase session pooler, `sslmode=require`),
`REDIS_URL` (Upstash `rediss://`), `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`
(LiveKit Cloud), `LIVEKIT_PUBLIC_URL` (ws URL of the cloud project), B2 storage values
(§3.2), `TRUSTED_HOSTS`, `backend_cors_origins` (only if ever needed), `ENVIRONMENT=production`.
Vercel gets: `NEXT_PUBLIC_WS_URL=wss://<service>.onrender.com`, `NEXT_PUBLIC_API_BASE` (if
used). `.env.paaS` template lives locally, gitignored — same discipline as `.env.prod`.

### 2.3 Parked: the VM playbook (Track B, when a bank card exists)

The Oracle/DuckDNS-VM/Caddy/R2 runbook from earlier revisions (VM provisioning, ufw,
`livekit.yaml`, `/rtc` proxy, keep-warm cron) stays in git history and in DEPLOYMENT.md
for the day a real debit card unlocks it — **zero code changes needed to move**; only
env values flip (storage provider, `LIVEKIT_URL`, domain).

---

## 3. Phase 3 — Go-live

### 3.1 Deployment path (chosen)

| | **Path C — split free PaaS ✅ chosen (D26)** | Path A — Docker Compose on a VM | ~~Path B~~ |
|---|---|---|---|
| What | Vercel + Render + Supabase + Upstash + LiveKit Cloud + B2 (§0.5) | Oracle Always Free, current [DEPLOYMENT.md](DEPLOYMENT.md) stack | folded into A |
| Ops burden | near zero (no server to patch) | low, needs a card | — |
| Always-on? | yes-if: keep-alive ping (fits 750 h budget) + healthy caps | yes, datacenter-grade | — |
| Verdict | ✅ launch now, $0, no card | 🔄 upgrade path when a card exists | — |

### 3.2 Repo changes needed for the PaaS deploy

> Full step-by-step: [DEPLOYMENT_PAAS.md](DEPLOYMENT_PAAS.md) (env var per service,
> wiring order, verify list) + fill-in template `.env.paaS.example`.

- **Vercel** (settings, not files): Root Directory = `frontend/`; env `API_INTERNAL_URL`
  + `NEXT_PUBLIC_WS_URL` — the `/api/v1/*` rewrite itself already exists in
  `next.config.ts` (no `vercel.json` needed).
- **Render:** `render.yaml` blueprint (web service from the backend Dockerfile, env table
  from the runbook, health check path `/api/health` with `SELECT 1` — §0.5, pre-deploy
  `alembic upgrade head`) and a Dockerfile CMD that honors `$PORT` (today it hardcodes
  8001; Render injects `$PORT`).
- **Storage (D24 amendment): ✅ shipped** — `STORAGE_PROVIDER=s3` is a generic
  S3-compatible provider (`S3_ENDPOINT`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
  `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, optional `S3_ADDRESSING_STYLE`, default
  path-style) covering Backblaze B2 and any other vendor; fail-fast validation
  stays. MinIO (dev/test) and R2 are unchanged.
- Cookie stays `SameSite=Lax` (proxy makes it same-site) — no auth rework by design.
- Drop from the old plan: Caddyfile `/rtc` route, LiveKit port publishing, ufw, DuckDNS
  A-record-at-deploy (all VM-only). DuckDNS custom domain = optional polish step.
- Fold infra specifics into DEPLOYMENT.md (rewrite it from VM-runbook → PaaS runbook).

### 3.3 First launch

1. Gate green + E2E green.
2. Connect repo: Vercel (frontend) + Render (backend, Docker) — first deploy from
   `master`.
3. Fill envs from `.env.paaS`; confirm fail-clearly checks fire, `/api/health` reports
   `environment: production` **and** is reachable from UptimeRobot.
4. Wire UptimeRobot (5-min `/api/health`) → verify Render never sleeps over 30 min and
   Supabase shows activity.
5. **B2 real smoke test** (never exercised against live B2): upload → Range download →
   presign → delete; counts appear in the B2 dashboard.
6. Two-device test from different networks: A/V + screen share (LiveKit minutes visible
   in the cloud dashboard).

### 3.4 Feature verification checklist (every feature, once manually)

- [ ] register / login / logout — cookies `Secure`, refresh rotation **through the Vercel proxy**
- [ ] create meeting, share link (D25), waiting room admit/decline, lock/unlock, end-for-all
- [ ] two-browser join from **different networks** — A/V both ways + screen share
- [ ] chat, host mute/remove
- [ ] exam mode: password gate, prejoin self-check, MediaPipe loads, proctoring flags reach host panel only
- [ ] report: integrity tiers (if T1), CSV + Word/Excel + PDF dossier, audit rows written
- [ ] evidence: capture → B2 upload → thumbnail in report → owner/host-only reads →
      Range playback → delete / legal hold
- [ ] invite: share link → incognito → register/login → lands back on `/room/<code>`;
      wrong password shows a clear server message (audit H4)
- [ ] DMs (host-enabled), settings page saves
- [ ] demo seed runs; Playwright green in CI
- [ ] UptimeRobot monitor healthy + an alert actually arrives (webhook/email)
- [ ] idle 30 min → next request still fast (keep-alive verified); LiveKit minute usage sane

### 3.5 Auto-deploy

Vercel (frontend) and Render (backend) both auto-deploy from `master` — free. CI remains
the gate before merge.

---

## 4. Phase 4 — Operations (all $0)

- **Backups** — nightly `pg_dump` from your PC (a small script; PC needn't be the server)
  → B2; restore drill once. Supabase dashboard export as a second path.
- **Updates** — push to `master` → platforms rebuild; rollback = redeploy previous build.
- **Monitoring** — UptimeRobot (5-min, doubles as keep-alive) → webhook alert; watch three
  dashboards weekly: Render instance hours (750), LiveKit minutes (5,000), B2 usage.
- **Abuse** — existing per-IP/per-user rate limits; add a signup toggle (B6) if spam shows.

---

## 5. Risks & honest limits

| Risk | Impact | Mitigation |
|---|---|---|
| Render 750 instance-h exhausted (e.g. second service added) | services suspended until next month | one service only; hours visible on the dashboard; the paid/VM upgrade is the escape hatch |
| LiveKit free 5,000 participant-min hard cap | new joins fail mid-month | usage dashboard weekly; it fails cleanly and never bills; Ship plan or VM later |
| Vercel/Render free = non-commercial | ToS issue **only** once revenue starts | launch/testing unaffected; upgrade the day the first customer pays |
| Supabase inactivity pause / pooler quirks | backend can't reach DB | health `SELECT 1` every 5 min; IPv4 session pooler + `sslmode=require`; manual resume from dashboard |
| Upstash 10k cmds/day | rate limits fail open (by design) | watch counter; downgrade is degradation, not outage |
| B2 fills (10 GB) or bucket exposed | uploads fail / data risk | private bucket, scoped app key, fail-clearly + retention sweep, alerts |
| Render "service-initiated traffic" suspension on heavy outbound egress | service paused | evidence egress is modest at our scale; move to VM path if it trips |
| No card ever | Oracle/R2 stay locked | whole stack is designed card-free; VM path is a pure env-swap later |
| Playwright covers core paths only | corner regressions | the existing gate (178+156) keeps guarding backend/frontend |

---

## Appendix — First 48 hours

1. **Create the 7 no-card accounts (§2.1, ~25 min)** — the only manual infra steps for now.
2. **Approve or decline the T1 trust proposal** (blocks Phase 1 item #1).
3. **Fix the audit findings** ([AUDIT.md](AUDIT.md) Top 10) — underway, gate green per commit.
4. Build the backlog (Phase 1 rows 3–9) → then deploy per §3.3.
5. DuckDNS custom domain on Vercel/Render — optional polish at the end.
