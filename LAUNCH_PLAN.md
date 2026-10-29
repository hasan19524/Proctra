# Proctra — Zero-Cost Launch Plan

**Goal:** production deployment with **$0/month** and every feature working.

Decisions (confirmed):

- **Hosting** — no credit card exists (student, $0): the Oracle/R2 signups that require
  one are paused. Chosen path: **own-machine server** (§0.5 Track A) now; Oracle Always
  Free later the moment a non-virtual bank debit card exists (§0.5 Track B).
- **Scope** — build the full product backlog **before** going live (phases below).
- **Domain** — free DuckDNS subdomain **`proctrahasan19524.duckdns.org`** (created ✅,
  currently pointing at the home public IP), auto-HTTPS via Caddy + Let's Encrypt.

Related docs: [DEPLOYMENT.md](DEPLOYMENT.md) (env tables, R2 checklist, go-live verify),
[DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md).

---

## 0. The $0 budget

| Need | Provider | Cost | Card? | Free-tier limit |
|---|---|---|---|---|
| Server | **Own PC** — Windows 11 Home (build 26200), 16 GB RAM, Docker Desktop/WSL2 (mirrored networking passes UDP through to LiveKit) | $0 | No | home power + ISP are your uptime; router forwards TCP 80/443 + UDP 50000–50099; upload bandwidth caps participants ≈ fine ≤ 10 video users |
| Server (upgrade) | Oracle Always Free `VM.Standard.A1.Flex` (**2 OCPU / 12 GB ARM** + 200 GB storage) — Track B, when a card exists | $0/mo forever | Yes — only real credit / "debit that functions as credit" (virtual, prepaid, single-use rejected) | Oracle halved this from 4 OCPU/24 GB in Jul 2026; idle ARM can be reclaimed → keep-warm cron (§4) |
| Domain | DuckDNS (`proctrahasan19524.duckdns.org`) ✅ | $0 | No | a handful of subdomains |
| TLS | Let's Encrypt (via Caddy, HTTP-01 on port 80) | $0 | No | auto-renewed |
| Object storage | **MinIO on the same machine** (D24 dev provider, opt-in for prod — §3.2) | $0 | No | your disk; Cloudflare R2 free tier (card required) is the Track B upgrade |
| CI | GitHub Actions (public repo) | $0 | No | unlimited minutes + free Linux arm64 runners |
| Monitoring | Uptime Kuma (self-hosted container) → Discord/Telegram webhook alerts | $0 | No | — |
| TURN (only if needed) | coturn on the same machine | $0 | No | uses your bandwidth |

**One-time: $0. Monthly: $0.** Deliberately avoided: paid R2 tier, SendGrid/Resend,
managed databases, CDNs, extra VMs — and anything whose free tier wants a card.

---

### 0.5 Hosting without a card (student edition)

Both original vendors gate their free tiers behind a payment method on file: Oracle
accepts only credit cards and debit "that function like credit cards" (virtual, prepaid
and single-use cards are rejected outright), and Cloudflare R2's free tier asks for a
card too. With no card, three honest tracks:

| | **Track A — own PC (chosen)** | **Track B — Oracle + bank debit** | **Track C — no-card PaaS** |
|---|---|---|---|
| Needs | this PC (16 GB RAM ✅), router admin, broadband | any non-virtual Visa/MC debit card | nothing |
| Cost | $0 forever | $0 forever | $0 (free tiers) |
| Features | ✅ **all** — identical Compose stack, LiveKit UDP, MinIO, Caddy/LetsEncrypt | ✅ all, datacenter-grade | ⚠️ Render sleeps after 15 min, no UDP (LiveKit Cloud caps), Backblaze B2 instead of R2, non-commercial ToS |
| Weakness | uptime = home power + ISP; PC can't sleep; one machine hosts dev too | needs the card | exam-day unreliability — demo-grade only |

**Track A is the plan** because it needs nothing and keeps every feature working.
**Track B is a pure upgrade later**: same stack, only `.env.prod` values change — no
code rework. Track C only if A fails the CGNAT check *and* no card ever materialises.

Track A pre-conditions (~15 min, mostly manual):

1. **CGNAT check** — compare the router admin WAN IP (`http://192.168.x.1` → status)
   with the public IP (`curl -s https://api.ipify.org`). Equal → ✅ publishable.
   Different → ISP CGNAT → fall back to B/C.
2. **Port forwards** — router → this PC: TCP 80, TCP 443, UDP 50000–50099.
3. **Always awake** — disable sleep/hibernate; DuckDNS updater cron using the token
   already saved in gitignored `.env.duckdns` (repoints automatically when the ISP
   rotates your IP).
4. **Storage** — MinIO container in the prod stack behind an explicit, fail-loud
   production opt-in (D24's fail-fast default stays off — §3.2).

Sections §2.2–§2.5 below describe the eventual Oracle VM (Track B) and are kept ready;
while no card exists, the identical `docker-compose.prod.yml` stack runs on this machine.

---

## 1. Phase 1 — Build the backlog (before launch)

Rule for every item: `./scripts/procto.ps1 check` stays green, the item ships with tests,
and CI (incl. Playwright once #8 lands) is green.

| # | Workstream | Done means | Size |
|---|---|---|---|
| 1 | **T1 trust layer** — ⚠️ *pending your approval* of the trust proposal you were reviewing | Heartbeat + SFU cross-checks, report integrity tiers, host "mark observed"; a missing/late clip is reported honestly and never implies cheating | L |
| 2 | **B1 security audit** | Background audit delivered (H1–H8, M1–M12, L1–L9, no IDOR found); fix pass in Top-10 order, SECURITY.md aligned at the end | M |
| 3 | **B4 host controls** | Host can globally disable + per-participant mute/cam/screen-share controls, enforced server-side, audited | M |
| 4 | **Evidence capture UI** (frontend client for the Phase-17 storage API — currently missing) | Clip/screenshot capture during exam, watermark + nonce, upload with retry/offline honesty, thumbnails in host report, owner/host-only access end-to-end | L |
| 5 | **B3 exports** | Word (.docx) + Excel (.xlsx) report exports and per-student PDF dossier; audit-logged (CSV already exists) | M |
| 6 | **B5 DMs + B6 settings page** | Host-enableable DMs between participants (toggle-only first); real settings page (profile, password, preferences) | M + M |
| 7 | **Invite & share polish** ✅ *(shipped, D25)* | Link share/copy (`navigator.share` → clipboard), `?next=` return-to after login/register, open-redirect guard — **no email anywhere** | S |
| 8 | **B2 demo data + G2 Playwright E2E** | Seed script (demo users/meetings/exam/report); Playwright covers register→join→report in CI | S + M |
| 9 | **G4 observability** | Uptime Kuma container, Docker log rotation, health monitoring, alert-by-email | S |

**Phase 1 exit:** every row shipped (or explicitly descoped by you), gate green, E2E green.
If you decline the T1 proposal, start with #2 (security audit).

---

## 2. Phase 2 — Infrastructure (Track A now, accounts ready for Track B)

> §2.2–2.5 are the **Track B (Oracle VM)** playbook, kept ready for when a card exists.
> Track A (own PC, §0.5) needs no account signup at all — its steps are in §0.5.

### 2.1 Accounts

1. ~~Oracle Cloud signup~~ — **paused**: needs a card (§0.5 Track B); resume the open
   signup tab when a non-virtual debit/credit card exists.
2. **DuckDNS** ✅ — `proctrahasan19524.duckdns.org` created; token stored in gitignored
   `.env.duckdns` for the updater cron.
3. ~~Cloudflare R2~~ — **paused**: free tier wants a card. Track A stores evidence in
   MinIO on the machine (D24 provider, prod opt-in §3.2); R2 is the Track B upgrade.
4. ~~Gmail app password~~ — **not needed**: invites are links, there is no mailer (D25).

### 2.2 VM provisioning (Oracle console)

- Region/AD **with A1 capacity** (if shape launch fails, switch region).
- Shape `VM.Standard.A1.Flex`, **2 OCPU / 12 GB RAM** (current Always Free maximum —
  Oracle halved the old 4 OCPU/24 GB in July 2026; our full stack needs ~3 GB, so this
  is comfortable), Ubuntu 24.04 aarch64, ~47–50 GB boot volume (all our images are
  multi-arch: python-slim, node:22-alpine, postgres, redis, livekit, caddy all build
  natively on ARM). Total free storage across volumes: 200 GB.
- VCN + internet gateway + public IP.
- **Security list ingress:** TCP 22 (your IP only), TCP 80 (Caddy cert issuance/renewal),
  TCP 443, UDP 50000–50099 (must match `rtc.port_range` in `livekit/livekit.yaml`),
  ICMP. Outbound: everything except port 25 (Oracle blocks it — irrelevant, we use 587).
- Separate `procto` user, SSH key auth, password login disabled.

### 2.3 VM hardening

- `ufw`: allow 22 (your IP), 80, 443, `50000:50099/udp`; enable.
- Docker Engine + compose plugin (get.docker.com supports arm64).
- `sshguard`/`fail2ban`, unattended-upgrades, Docker json-file log rotation
  (`max-size=10m`, `max-file=5`).

### 2.4 Secrets on the VM

`.env.prod` lives **on the VM only** (gitignored; never committed — see DEPLOYMENT.md §1
for the full table). Generate fresh: `SECRET_KEY` (64 chars), LiveKit key pair,
`POSTGRES_PASSWORD`, MinIO keys (Track A; `R2_*` only on Track B — no SMTP at all, D25),
`DOMAIN`, `TRUSTED_HOSTS`,
`NEXT_PUBLIC_WS_URL=wss://<your-subdomain>.duckdns.org`, `LIVEKIT_PUBLIC_URL` (§2.5).

### 2.5 LiveKit production config

- Real keys in `livekit/livekit.yaml` matching env; `development: false`;
  `use_external_ip: true` (ICE candidates must advertise the VM's public IP); port range
  identical to the firewall rule.
- Signaling over TLS: route `/rtc` (WebSocket) through Caddy to `livekit:7880` so
  browsers connect via `wss://<your-subdomain>.duckdns.org` → set `LIVEKIT_PUBLIC_URL`
  accordingly (DEPLOYMENT.md §2 explains the internal/public URL split). Media rides the
  public UDP range directly.
- **Verify from outside your network** (cellular!): two-device A/V + screen share.

---

## 3. Phase 3 — Go-live

### 3.1 Deployment paths (pick one)

| | **Path A — Docker Compose** | **Path B — Native, zero Docker** | **Path C — PaaS fallback** |
|---|---|---|---|
| What | Current [DEPLOYMENT.md](DEPLOYMENT.md) stack on the Oracle VM | Same VM, plain systemd units: apt Postgres/Redis/Caddy, LiveKit static binary (arm64), `uv`+uvicorn, `node .next/standalone/server.js` | Frontend→Vercel, backend→Render, video→LiveKit Cloud, DB→Neon/Upstash free |
| Ops burden | Low | Medium (units + deploy script) | Near zero |
| Always-on? | Yes | Yes | ❌ 15-min sleep + cold starts; Render free Postgres **deletes itself after 30 days**; 5 GB bandwidth/mo; no UDP (LiveKit Cloud free minute caps); Vercel/Render free tiers are **non-commercial** |
| Verdict | ✅ default | ✅ use if Docker is the problem | ⚠️ demo-grade only — not exam-day material |

**Path A** needs no new work (documented end-to-end). **Path B** removes Docker from
production entirely — same `.env.prod`, same `Caddyfile`, same `livekit.yaml`; the
differences are a `deploy.sh` (uv sync → alembic upgrade → restart units), systemd unit
files I'll write when we get there, and UptimeRobot (free, external) instead of the Kuma
container. Local dev/tests keep Docker regardless (the test gate needs Postgres/Redis/
MinIO). **Path C** exists only as a last resort if Track A fails the CGNAT check **and**
no card materialises (§0.5):
every feature still works, but exam-day reliability drops hard. Default: **A**, switch to
**B** the moment Docker gets in the way.

### 3.2 Repo changes needed for the deploy

- `docker-compose.prod.yml`: publish LiveKit ports (UDP media range; signaling if not
  proxied) — currently commented with "prefer exposing at the host/edge".
- `Caddyfile`: add an `/rtc*` → `reverse_proxy livekit:7880` route for wss signaling
  (Caddy upgrades WebSockets automatically). `{$DOMAIN:localhost}` already works with
  DuckDNS.
- **Track A only:** an explicit, fail-loud env opt-in so MinIO may run as production
  storage (D24's "minio in production" refusal stays the default), a DuckDNS updater
  cron reading gitignored `.env.duckdns`, and Windows power settings with sleep off.
  Dev/test and prod share one machine → one Compose stack at a time on the usual ports
  (the always-on prod stack doubles as the test target).
- Fold this plan's infra specifics (hosting track, DuckDNS, storage provider) into
  DEPLOYMENT.md once executed.

### 3.3 First launch

1. Pre-flight: gate green, E2E green, `docker compose -f docker-compose.prod.yml config`
   passes on the VM.
2. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
3. Confirm fail-clearly behaviour, `migrate` exits 0, `/api/health` reports
   `environment: production`.
4. **Storage smoke test** (MinIO on Track A, R2 on Track B — never exercised against the
   real store before): upload → download (Range) → presign → delete through the API;
   object appears in the store dashboard. (DEPLOYMENT.md has the full checklist.)
5. `https://<your-subdomain>.duckdns.org` serves, browser shows the camera prompt (secure
   origin).

### 3.4 Feature verification checklist (every feature, once manually)

- [ ] register / login / logout — cookies `Secure`, refresh rotation
- [ ] create meeting, share link, waiting room admit/decline, lock/unlock, end-for-all
- [ ] two-browser join from **different networks** — A/V both ways + screen share
- [ ] chat, host mute/remove
- [ ] exam mode: password gate, prejoin self-check, MediaPipe loads (~44 MB assets),
      proctoring flags reach host panel only
- [ ] report: integrity tiers (if T1), CSV + Word/Excel + PDF dossier, audit rows written
- [ ] evidence: capture → upload → thumbnail in report → owner/host-only reads →
      Range playback → delete / legal hold → retention sweep runs
- [ ] invite: share link from device A → open in incognito → register/login → lands back
      on `/room/<code>`; wrong password shows a clear server message (audit H4)
- [ ] DMs (host-enabled), settings page saves
- [ ] demo seed runs; Playwright green in CI
- [ ] Uptime Kuma: monitors `/api/health` + site every 60 s, webhook alert received
      (Discord/Telegram — no email anywhere, D25)

### 3.5 Optional: auto-deploy

GitHub Actions job on push to `master` → SSH → `git pull` + compose up (free for public
repos, includes free arm64 runners if we later prebuild images to GHCR). Manual
`git pull` deploys are fine at launch.

---

## 4. Phase 4 — Operations (all $0)

- **Backups** — nightly `pg_dump` + weekly pgdata tar via cron → push to the object store
  (MinIO Track A / R2 Track B; aws-cli, free), 14–30 day retention; **restore drill** once
  into a staging DB.
- **Updates** — CI first, then on the host: `git pull` → `up -d --build` (migrate service
  runs automatically). Rollback = `git checkout <sha>` → up.
- **Keep the ARM instance warm** (Track B) — Oracle reclaims persistently idle A1
  capacity; a tiny cron load (e.g. hitting `/api/health` every few minutes) keeps it out
  of the idle bucket.
- **Monitoring** — Kuma heartbeats → Discord/Telegram webhook alerts; weekly
  `docker system df`.
- **Abuse** — existing per-IP/per-user rate limits; add a signup toggle (B6) if spam shows.

---

## 5. Risks & honest limits

| Risk | Impact | Mitigation |
|---|---|---|
| Home PC off / power or ISP outage | meetings drop while it's down | sleep disabled + auto-start compose; honest reconnect states; Track B upgrade when a card exists |
| Home upload bandwidth shared with the household | video quality drops with many participants | ≤ 10 video participants comfortably; screen-share-first mode; Move to Oracle (Track B) when a card exists |
| No card | Oracle + R2 signups blocked (virtual/prepaid rejected) | Track A needs no card at all; a real bank debit later unlocks B with zero code changes |
| Evidence fills the home disk (R2: 10 GB) | uploads fail (fail-clearly) | 90-day retention sweeper, host deletions, disk-usage alarm → R2 paid tier later |
| Oracle trims the free tier again (it quietly halved A1 in Jul 2026) *(Track B)* | less headroom | stack needs ~3 GB / ~1.5 OCPU — survives another halving; Track C is the escape hatch |
| Oracle reclaims idle ARM / quota quirks *(Track B)* | downtime | warm-up cron; account stays active; backups make worst case recoverable |
| A1 capacity scarce in some regions *(Track B)* | signup friction | pick a region with stock |
| No TURN at first | a few symmetric-NAT users can't publish media | add coturn on the same host (free) when reported |
| Single host | all services share one fate | healthchecks + restart policies + backups; acceptable for launch scale |
| No CDN | distant users get higher latency | fine at small scale; single-hop LiveKit |
| Playwright covers core paths only | corner regressions | the existing 323-test gate keeps guarding backend/frontend |

---

## Appendix — First 48 hours

1. **Track A setup (§0.5)** — CGNAT check + port forwards + sleep-off; this is the
   hosting gate (Oracle stays parked until a card exists).
2. DuckDNS ✅ done (token in `.env.duckdns`); R2/Oracle paused — nothing else to sign up
   for right now.
3. **Approve or decline the T1 trust proposal** (blocks Phase 1 item #1).
4. Fix the delivered audit findings (Phase 1 #2) in Top-10 order, gate green per commit.
5. When Track A is live: provision the stack per DEPLOYMENT.md while Phase 1 continues.
