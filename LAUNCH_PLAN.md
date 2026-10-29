# Proctra — Zero-Cost Launch Plan

**Goal:** production deployment with **$0/month** and every feature working.

Decisions (confirmed):

- **Hosting** — Oracle Cloud *Always Free* VM (ARM A1 shape). Signup needs a card for
  identity verification but is never charged.
- **Scope** — build the full product backlog **before** going live (phases below).
- **Domain** — free DuckDNS subdomain (`proctra.duckdns.org`), auto-HTTPS via Caddy +
  Let's Encrypt.

Related docs: [DEPLOYMENT.md](DEPLOYMENT.md) (env tables, R2 checklist, go-live verify),
[DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md).

---

## 0. The $0 budget

| Need | Provider | Cost | Card? | Free-tier limit |
|---|---|---|---|---|
| Server | Oracle Always Free `VM.Standard.A1.Flex` (up to 4 OCPU / 24 GB ARM) | $0/mo forever | Yes (identity check only) | Always Free quota; idle ARM instances can be reclaimed → we keep it warm (§4) |
| Domain | DuckDNS (`proctra.duckdns.org`) | $0 | No | a handful of subdomains |
| TLS | Let's Encrypt (via Caddy, HTTP-01 on port 80) | $0 | No | auto-renewed |
| Object storage | Cloudflare R2 **free tier** | $0 | Card on file likely | ~10 GB storage + 1M Class A / 10M Class B ops per month (verify in dashboard) |
| Email | Gmail SMTP + app password | $0 | No (needs 2FA on the Google account) | 500 msgs/day |
| CI | GitHub Actions (public repo) | $0 | No | unlimited minutes + free Linux arm64 runners |
| Monitoring | Uptime Kuma (self-hosted container) | $0 | No | — |
| TURN (only if needed) | coturn on the same VM | $0 | No | uses the VM's bandwidth |

**One-time: $0. Monthly: $0.** Deliberately avoided: paid R2 tier, SendGrid/Resend,
managed databases, CDNs, extra VMs.

---

## 1. Phase 1 — Build the backlog (before launch)

Rule for every item: `./scripts/procto.ps1 check` stays green, the item ships with tests,
and CI (incl. Playwright once #8 lands) is green.

| # | Workstream | Done means | Size |
|---|---|---|---|
| 1 | **T1 trust layer** — ⚠️ *pending your approval* of the trust proposal you were reviewing | Heartbeat + SFU cross-checks, report integrity tiers, host "mark observed"; a missing/late clip is reported honestly and never implies cheating | L |
| 2 | **B1 security audit** | Full authz/threat pass (security-auditor), every finding fixed, SECURITY.md updated | M |
| 3 | **B4 host controls** | Host can globally disable + per-participant mute/cam/screen-share controls, enforced server-side, audited | M |
| 4 | **Evidence capture UI** (frontend client for the Phase-17 storage API — currently missing) | Clip/screenshot capture during exam, watermark + nonce, upload with retry/offline honesty, thumbnails in host report, owner/host-only access end-to-end | L |
| 5 | **B3 exports** | Word (.docx) + Excel (.xlsx) report exports and per-student PDF dossier; audit-logged (CSV already exists) | M |
| 6 | **B5 DMs + B6 settings page** | Host-enableable DMs between participants (toggle-only first); real settings page (profile, password, preferences) | M + M |
| 7 | **G3 invite emails** | SMTP mailer (env-configured → Gmail app password), invite + reminder templates, delivery logged and resendable | M |
| 8 | **B2 demo data + G2 Playwright E2E** | Seed script (demo users/meetings/exam/report); Playwright covers register→join→report in CI | S + M |
| 9 | **G4 observability** | Uptime Kuma container, Docker log rotation, health monitoring, alert-by-email | S |

**Phase 1 exit:** every row shipped (or explicitly descoped by you), gate green, E2E green.
If you decline the T1 proposal, start with #2 (security audit).

---

## 2. Phase 2 — Infrastructure (start account signup on day 1)

> Oracle account approval can take days — kick it off immediately, in parallel with Phase 1.

### 2.1 Accounts (day 1, ~30 min, all $0)

1. **Oracle Cloud** signup — identity check with card; stay on Always Free (trial credits
   expire, Always Free resources remain).
2. **DuckDNS** account → create `proctra.duckdns.org` → A record = VM public IP.
3. **Cloudflare** → enable R2 → private bucket (e.g. `procto-evidence`) → S3 API token
   scoped read/write to that bucket → record the four `R2_*` values. Confirm the free-tier
   caps shown in your dashboard.
4. **Gmail** → enable 2-Step Verification → create an **app password** (becomes
   `SMTP_PASSWORD`; never your login password).

### 2.2 VM provisioning (Oracle console)

- Region/AD **with A1 capacity** (if shape launch fails, switch region).
- Shape `VM.Standard.A1.Flex`, **4 OCPU / 24 GB RAM** (Always Free maximum),
  Ubuntu 24.04 aarch64, ~47 GB boot volume (all our images are multi-arch: python-slim,
  node:22-alpine, postgres, redis, livekit, caddy all build natively on ARM).
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
`POSTGRES_PASSWORD`, `R2_*`, SMTP values, `DOMAIN`, `TRUSTED_HOSTS`,
`NEXT_PUBLIC_WS_URL=wss://proctra.duckdns.org`, `LIVEKIT_PUBLIC_URL` (§2.5).

### 2.5 LiveKit production config

- Real keys in `livekit/livekit.yaml` matching env; `development: false`;
  `use_external_ip: true` (ICE candidates must advertise the VM's public IP); port range
  identical to the firewall rule.
- Signaling over TLS: route `/rtc` (WebSocket) through Caddy to `livekit:7880` so
  browsers connect via `wss://proctra.duckdns.org` → set `LIVEKIT_PUBLIC_URL`
  accordingly (DEPLOYMENT.md §2 explains the internal/public URL split). Media rides the
  public UDP range directly.
- **Verify from outside your network** (cellular!): two-device A/V + screen share.

### 2.6 Email creds

`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD` (app password),
`EMAIL_FROM` (must be the Gmail address — Gmail only sends as the authenticated user).
The mailer code itself ships in Phase 1 #7; `.env.example` gets the SMTP block then.

---

## 3. Phase 3 — Go-live

### 3.1 Repo changes needed for the single-VM deploy

- `docker-compose.prod.yml`: publish LiveKit ports (UDP media range; signaling if not
  proxied) — currently commented with "prefer exposing at the host/edge".
- `Caddyfile`: add an `/rtc*` → `reverse_proxy livekit:7880` route for wss signaling
  (Caddy upgrades WebSockets automatically). `{$DOMAIN:localhost}` already works with
  DuckDNS.
- Fold this plan's infra specifics (Oracle, DuckDNS, R2 free tier) into DEPLOYMENT.md
  once executed.

### 3.2 First launch

1. Pre-flight: gate green, E2E green, `docker compose -f docker-compose.prod.yml config`
   passes on the VM.
2. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
3. Confirm fail-clearly behaviour, `migrate` exits 0, `/api/health` reports
   `environment: production`.
4. **R2 real smoke test** (the only thing never exercised against live R2): upload →
   download (Range) → presign → delete through the API; counts appear in the R2
   dashboard. (DEPLOYMENT.md has the full R2 checklist.)
5. `https://proctra.duckdns.org` serves, browser shows the camera prompt (secure origin).

### 3.3 Feature verification checklist (every feature, once manually)

- [ ] register / login / logout — cookies `Secure`, refresh rotation
- [ ] create meeting, share link, waiting room admit/decline, lock/unlock, end-for-all
- [ ] two-browser join from **different networks** — A/V both ways + screen share
- [ ] chat, host mute/remove
- [ ] exam mode: password gate, prejoin self-check, MediaPipe loads (~44 MB assets),
      proctoring flags reach host panel only
- [ ] report: integrity tiers (if T1), CSV + Word/Excel + PDF dossier, audit rows written
- [ ] evidence: capture → upload → thumbnail in report → owner/host-only reads →
      Range playback → delete / legal hold → retention sweep runs
- [ ] invite email arrives — test Gmail **and** one non-Gmail provider
- [ ] DMs (host-enabled), settings page saves
- [ ] demo seed runs; Playwright green in CI
- [ ] Uptime Kuma: monitors `/api/health` + site every 60 s, alert email received

### 3.4 Optional: auto-deploy

GitHub Actions job on push to `master` → SSH → `git pull` + compose up (free for public
repos, includes free arm64 runners if we later prebuild images to GHCR). Manual
`git pull` deploys are fine at launch.

---

## 4. Phase 4 — Operations (all $0)

- **Backups** — nightly `pg_dump` + weekly pgdata tar via cron → push to R2
  (aws-cli/rclone, free), 14–30 day retention; **restore drill** once into a staging DB.
- **Updates** — CI first, then on VM: `git pull` → `up -d --build` (migrate service runs
  automatically). Rollback = `git checkout <sha>` → up.
- **Keep the ARM instance warm** — Oracle reclaims persistently idle A1 capacity; a tiny
  cron load (e.g. hitting `/api/health` every few minutes) keeps it out of the idle bucket.
- **Monitoring** — Kuma heartbeats → Gmail SMTP alerts; weekly `docker system df`.
- **Abuse** — existing per-IP/per-user rate limits; add a signup toggle (B6) if spam shows.

---

## 5. Risks & honest limits

| Risk | Impact | Mitigation |
|---|---|---|
| Oracle reclaims idle ARM / quota quirks | downtime | warm-up cron; account stays active; backups make worst case recoverable |
| A1 capacity scarce in some regions | signup friction | pick a region with stock |
| R2 free tier (~10 GB) fills with evidence | uploads fail (fail-clearly) | 90-day retention sweeper, host deletions, dashboard alarm → paid tier is the escape hatch |
| Gmail 500/day + consumer sending reputation | invites land in spam | Gmail handles SPF/DKIM; templates stay simple → upgrade path: Resend free 3k/mo |
| No TURN at first | a few symmetric-NAT users can't publish media | add coturn on the same VM (free) when reported |
| Single VM | all services share one fate | healthchecks + restart policies + backups; acceptable for launch scale |
| No CDN | distant users get higher latency | fine at small scale; single-hop LiveKit |
| Playwright covers core paths only | corner regressions | the existing 323-test gate keeps guarding backend/frontend |

---

## Appendix — First 48 hours

1. **Start Oracle signup now** (approval is the long pole).
2. DuckDNS + Cloudflare R2 + Gmail app password (~30 min total).
3. **Approve or decline the T1 trust proposal** (blocks Phase 1 item #1).
4. Begin Phase 1 with item #2 (security audit) unless T1 is approved.
5. When Oracle approves: provision VM (§2.2–2.3) while Phase 1 continues.
