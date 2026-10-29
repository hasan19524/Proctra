# Proctra — Security & Product Audit (B1 input)

**Date:** 2026-10-29 · **Method:** static read-only review of `backend/app/**`,
`frontend/src/**`, `DECISIONS.md`, `SECURITY.md`, `ARCHITECTURE.md` (shell execution was
permission-denied in the agent sandbox, so ruff/vitest were not re-run by the reviewer —
the main gate covers that separately).

**Overall:** the backend authorization model is strong — every route family re-derives
identity/role server-side, host-only data (`proctor.flag`, host-only notes, reports,
evidence files) is gated consistently, and **no IDOR** was found in
meetings/participants/files/reports. The serious problems are (a) credential leakage
through WS query strings, (b) exam-integrity gates that exist in docs but not in the join
path, and (c) a frontend that silently drops every server error frame, producing dead-end
flows.

---

## HIGH

### H1 — WS access token *and* meeting/exam password travel in the URL query string
`backend/app/ws/gateway.py:739-741` (`token`, `password` Query params),
`frontend/src/lib/ws.ts:35-41` (`url.searchParams.append("password", password)`).
Uvicorn/reverse-proxy access logs record the full request target, so every WS upgrade
persists the student's exam password and a 15-min bearer token in plaintext logs; anything
that mirrors URLs (error trackers, APM) leaks them too. Violates SECURITY.md §5 ("join
secrets are never logged").
**Fix:** pass secrets via a POST-minted single-use ticket or the `Sec-WebSocket-Protocol`
header, and scrub query strings from access logs.

### H2 — Exam access is "shared password only"; the invite roster is never enforced at join
`backend/app/ws/gateway.py:786-817`, `backend/app/api/v1/meetings.py:124-150` check only
status/lock/password/waiting — `MeetingInvite` is consulted *only* by
`proctor_service.build_report` (`proctor_service.py:275-288`).
Anyone who registers and learns the exam password joins; the report simply lists them as
an extra PRESENT student — the roster cannot prevent uninvited takers.
**Fix:** for `kind="exam"`, reject joins whose user email is not in `meeting_invites`
(or issue per-student join tokens).
**⚠️ Plan note (post-D25):** conflicts with "invites are the link". Resolution chosen:
keep links, but (a) **exam meetings default the waiting room ON** so the host admits each
student by name, and (b) reports flag roster mismatches as `UNINVITED` instead of silently
folding extras into PRESENT — enforcement by host + honest reporting, no email needed.

### H3 — No server-side proctoring watchdog: a student who blocks the engine scores a clean 0
The gateway accepts `proctor.event` only when the client sends it
(`gateway.py:435-496`); the frontend engine (`use-proctoring.ts:64-90`,
`lib/proctor/engine.ts`) has no heartbeat/"engine started" frame, and the server records
nothing when zero events arrive. Blocking `/mediapipe-wasm` in DevTools (or not running
the JS) yields `cheating_score=0, event_count=0` — indistinguishable from a flawless exam;
`proctor-panel.tsx:128-133` even claims "the vision model is watching every student".
**Fix:** require a periodic `proctor.heartbeat` while `proctoring_enabled`, and surface
"no telemetry" as a distinct report status (pattern already exists: `upload_status`
failed/missing).

### H4 — Wrong meeting/exam password is a dead end: every server error frame is silently dropped
`frontend/src/lib/ws.ts:32` treats close 4003 (`wrong_password`,
`meeting_password_required`, `meeting_locked` — `gateway.py:800-808`) as fatal → generic
`failed`; `use-meeting-ws.ts:180-314` never subscribes to `error`;
`use-livekit-room.ts:207-209` collapses the token 403 into `status="failed"`;
`in-call-session.tsx:83-92` shows only a generic toast. A mistyped password lands the
student in the in-call shell with no media, no explanation, no path back to the lobby.
**Fix:** subscribe to `error` frames, route 403/wrong-password back to `PreJoinLobby` with
the server's message.

### H5 — No password reset or change-password flow exists anywhere
`backend/app/api/v1/auth.py` exposes only register/login/refresh/logout/logout-all/me;
`frontend/src/app/profile/page.tsx` is read-only. A forgotten password permanently orphans
an account with live exam history.
**Fix:** token-based reset (rate-limited, uniform responses) + profile "change password"
calling `logout_all`. **Plan note:** delivery needs a channel — per D25 this ships with its
own decision (transactional provider), not an SMTP revival by stealth.

### H6 — Registration discloses whether an email is registered
`backend/app/services/auth_service.py:75-77` → `409 "An account with this email already
exists"`, contradicting SECURITY.md §1 ("responses do not reveal whether an email exists").
**Fix:** uniform 201-style response, or explicitly amend SECURITY.md if enumeration is
accepted (recommendation: uniform response).

### H7 — Host "mute participant" is advisory only; not enforced at the SFU
`gateway.py:572-596` audits + broadcasts `participant.muted`; the frontend turns the mic
off locally (`in-call-session.tsx:122-125`). `sfu_service.py` implements only
remove/close-room; token mint grants `can_publish=True` to everyone
(`meetings.py:157-165`). A muted student simply re-enables their publication.
**Fix:** LiveKit `mute_published_track` server-side on `mute_participant`, and/or
publish-limited tokens for muted participants.

### H8 — On phones, users with meeting history cannot create a meeting at all
`frontend/src/app/page.tsx:167` — header "New meet" is `hidden … sm:flex`; the only other
create button lives in the empty state (`page.tsx:318-330`) which doesn't render once
`recent.length > 0`.
**Fix:** compact icon "New meet" button below `sm`.

---

## MEDIUM

- **M1** — All server `error` frames invisible beyond H4: `use-meeting-ws.ts` has no
  `socket.on("error")`; server emits them at `gateway.py:286-296,309-319,1006,1092-1101`
  (invalid_message, permission_denied, rate_limited…). Chat/note/rate-limit failures fail
  silently. **Fix:** one `error` handler → toast `payload.message`.
- **M2** — Phase 17 evidence pipeline has **no client**: no `MediaRecorder|upload|filesApi`
  anywhere in `frontend/src`; `lib/api.ts` has no files API. `clip_status` in CSVs will
  always be empty. **Fix:** `filesApi` + clip capture on proctor events + evidence viewer.
- **M3** — A removed exam student can immediately rejoin (`gateway.py:598-633` removes
  only sockets/Presence; rejoin re-admits at `786-817`). **Fix:** persist removal per
  (meeting, user) and reject reconnects for exams.
- **M4** — Next-served HTML has no CSP/X-Frame-Options (`frontend/next.config.ts:5-18`);
  the backend `SecurityHeadersMiddleware` covers API responses only. **Fix:** mirror the
  policy in `next.config.ts` `headers()`.
- **M5** — Lobby password UX ignores `has_password` (`room/[code]/page.tsx:127-138` never
  passes it; `prejoin-lobby.tsx:335-352` always shows "(if required)"; wrong password only
  discovered post-Join via H4). **Fix:** render/require the field iff `has_password`.
- **M6** — Dead controls: home "Help" (`page.tsx:176-178`), Previous/Next week
  (`page.tsx:229-241`, handlers missing, week strip static), captions/settings demo toasts
  (`in-call-view.tsx:440-446`), "Add people" demo toast (`in-call-view.tsx:464` — ✅ fixed
  this sprint). **Fix:** wire or hide.
- **M7** — Settings page fabricates state (`settings/page.tsx:55-91`: Notifications
  "On/On", Privacy "Enabled", "Audit logging: Enabled" — static text, no backend).
  **Fix:** remove fake cards or wire real preferences (B6).
- **M8** — Audit gaps: login/logout/refresh failures, WS connect/reject (wrong-password
  attempts!), LiveKit token mints, meeting creation are not audited (lock/end/mute/remove/
  files/report are). **Fix:** audit rows for auth outcomes + WS handshake rejections.
- **M9** — Report timeline measured from meeting **creation**: `started_at`
  (`models/meeting.py:52`) is never assigned; `proctor_service.py:42-54` falls back to
  `created_at` → "minute 65" in a 5-minute exam. **Fix:** stamp `started_at`/`live` on
  first non-host join.
- **M10** — `join.request` broadcasts to every participant (`gateway.py:842-848`;
  `_deliverable` filters `proctor.flag` etc. but not this) → students learn who is trying
  to join. **Fix:** host-only relay filter.
- **M11** — Rate-limit gaps: no per-user buckets on `note.save`/`chat.send` beyond the
  8/s flood; `file hold/delete`, `logout_all` unlimited; login per-IP only (comment defers
  per-email); limiter fails open on Redis outage; zset member `str(now)` dedupes
  same-timestamp events (`ratelimit.py:38-51`).
- **M12** — In-call layout breaks ≤390px: panels `w-96 max-w-full shrink-0` squeeze the
  stage to zero instead of overlaying; `UtilityCluster` (`absolute right-3 bottom-3`)
  overlaps the control dock. **Fix:** overlay panels on small screens, reserve bottom
  padding for the cluster.

---

## LOW

- **L1** — Access JWT survives logout ≤15 min (no jti denylist); open WS sessions never
  revoked (auth is handshake-once).
- **L2** — Evidence uploads accepted on ended meetings (`files.py:120-126`).
- **L3** — LiveKit grants uniformly `can_publish` + `can_publish_data`; second tab of one
  account collides on identity = user id (D19 caveat).
- **L4** — "Live" badge lies: meetings never leave `waiting` (`page.tsx:293-300`).
- **L5** — `CO_HOST` documented (D8/SECURITY.md §2) but unimplemented; `_require_host_report`
  compares `host_id` only → future co-hosts 403 reports.
- **L6** — Notes tabs: `role="tab"` without `tabpanel`/`aria-controls`; disabled
  "More actions" placeholder buttons add screen-reader noise.
- **L7** — WS origin check skipped when no `Origin` header (`gateway.py:747-749`) — token
  alone suffices from non-browser clients.
- **L8** — Dead/micro: `meetingsApi.report()` uncalled; `snapshot` spam costs a DB
  round-trip per `sync`; client code regex `[a-z2-9]` admits letters the server excludes;
  `shadcn` CLI is a runtime dependency (belongs in devDependencies).
- **L9** — Dependencies clean (locked floors, modern majors); watch: shadcn runtime dep.

---

## POSITIVE (verified)

- **No IDOR**: owner-or-host on every file read path incl. Range/presign, 404 not 403 as
  oracle-free; reports host-only re-derived server-side; host actions re-derive role from
  Postgres per action; proctor events can only flag the sender.
- **WS hardening above average:** origin allow-list, per-IP handshake budget before any
  DB/Argon2 work, per-(user,meeting) join budget bounding password guesses, token-bucket
  flood control, waiting-room frame allowlist, host-only relay filtering.
- **Auth core solid:** Argon2id + timing-equalized unknown-email login; refresh rotation
  with atomic CAS + reuse-family revocation; httpOnly SameSite=Lax cookie (Secure in
  prod); JWT algorithm allowlist + prod dev-secret refusal; CORS wildcard rejected; no
  state-changing GETs.
- **Injection/XSS:** no `dangerouslySetInnerHTML` with data; React text nodes for
  chat/notes; parameterized ORM only; UUID storage keys with sanitized filenames; magic-
  byte sniffing with per-purpose caps.
- **Proctor scoring server-authoritative:** whitelist + clamp + sanitized detail +
  server-side points/minute; report CSV via `csv` module.
- **Tests real:** 19 backend modules + vitest suites (ws, hooks, detector, panels,
  auth pages).

---

## Fix order (agreed Top 10)

1. **H1** — get password/token out of WS URLs (scrub access logs).
2. **H3** — proctor heartbeat/watchdog + "no telemetry" report status.
3. **H2** — exam roster handling (per D25 resolution: waiting-room default + `UNINVITED`).
4. **H4 + M1** — subscribe to `error` frames; wrong password/locked → back to lobby.
5. **H5** — password reset + change password (delivery = its own decision).
6. **H7** — enforce mute at LiveKit.
7. **H8** — restore "New meet" CTA below `sm`.
8. **M3** — persisted exam removal (no rejoin after kick).
9. **M9** — stamp `started_at`/`live` on first join.
10. **M2** — wire the evidence pipeline (or descope Phase 17 claims explicitly).

Then M4–M12, then L items as cleanup. Every fix: `./scripts/procto.ps1 check` green.
