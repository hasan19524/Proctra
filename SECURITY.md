# Procto — Security

Principle: **security belongs in the backend.** Frontend checks are UX only; every
sensitive operation is validated and authorized server-side.

Scope: what is needed for a trustworthy meeting platform. No speculative features.

## 1. Authentication

- Email + password. Passwords hashed with **Argon2id** (memory-hard, modern default),
  never reversible, never logged.
- Minimum password length enforced server-side (and mirrored in the UI).
- Login/registration responses do not reveal whether an email exists (uniform errors).
- Session model:
  - **Access token**: JWT, 15-minute expiry, held in frontend memory (not localStorage).
  - **Refresh token**: opaque random string, delivered in an **httpOnly + SameSite**
    cookie, stored **hashed** (SHA-256) in Postgres, rotated on every use, revocable
    (`revoked_at`), with reuse detection invalidating the family.
- Logout revokes the refresh token server-side.

## 2. Authorization (separate from authentication)

Roles in the meeting domain: `HOST`, `CO_HOST`, `PARTICIPANT` (platform role: `USER`).

- Authorization lives in **services**, never in route/WS handler code alone.
- Never trust a frontend-provided role, participant id, or permission flag.
- Host-only operations (lock, end meeting, remove/mute participant, promote co-host,
  waiting-room approval, permission toggles) re-derive the caller's role from the DB
  on every call.
- LiveKit tokens are minted only after authorization; a client cannot grant itself
  publish rights.

## 3. Meeting security (Phase 13, foundations defined now)

| Control | Mechanism |
|---|---|
| Meeting password | Argon2id hash in `meetings.password_hash`; verified on join |
| Waiting room | join is admitted only after a host approval event |
| Meeting lock | server rejects any new join while `locked = true` |
| Join token | short-lived, meeting-scoped, identity-bound |
| Session expiry | access JWT expiry + LiveKit token TTL + meeting `ended_at` checks |
| Rate limiting | Redis sliding window on login, register, WS connect, join attempts |
| Input validation | Pydantic schemas on every REST body; WS payloads validated per event type |
| WS authentication | token validated during the upgrade handshake; reconnects re-authenticate |
| Audit logging | `audit_logs` for security-relevant actions (lock, remove, permission change) |
| Exam meeting password | `kind = 'exam'` creation requires a password (min 8 chars), Argon2id-hashed, verified on join |
| Evidence storage | Private object-store buckets (MinIO dev / R2 prod); server-side authz on every read (owner or host); credentials never reach the frontend |
| Evidence audit | `audit_logs` records `report_download`, `file_upload`, `file_download`, `file_delete`, `file_hold` |

## 4. Transport & browser hardening

- Cookies: `httpOnly`, `SameSite=Lax`, `Secure` outside local dev.
- CORS: explicit allow-list from environment configuration; credentials only for the
  known frontend origin.
- WebSocket origin checked on upgrade.
- Security headers (CSP, X-Frame-Options, etc.) applied at the Next.js / reverse-proxy
  layer as the app matures.
- No secrets in the repository: everything comes from `.env` (git-ignored) with
  `.env.example` documenting required names.

## 5. Data handling

- Passwords, refresh tokens, and join secrets are never logged.
- Messages/notes are scoped to their meeting in every query — no cross-meeting reads.
- Evidence/attachment uploads (D24): Content-Length pre-check plus per-purpose byte
  caps (clip 50 MB, screenshot 10 MB, attachment 25 MB), magic-byte content sniffing
  (the declared Content-Type is ignored), randomized UUID object keys in private
  buckets, storage credentials server-side only. Reads go through the backend so
  every access is authorized and audit-logged; another student's file is a 404
  (no existence oracle). Retention cleanup skips files under `legal_hold`.
- A missing or failed clip upload is reported honestly (`failed`/`missing`) and
  never treated as evidence of cheating by itself.
- Errors returned to clients are generic; detail goes to structured server logs.

## 6. Proctoring trust model (Phase 16)

Exam meetings (`kind = 'exam'`, `proctoring_enabled`) follow the house rule: the client
observes, the server decides.

| Rule | Mechanism |
|---|---|
| Video never leaves the device | The face landmarker (MediaPipe WASM + model) is self-hosted under `/public` and runs on-device; only classified signal labels are sent over the app WebSocket. No CDN, no API keys, no server-side video processing or storage. |
| The client only reports observations | `proctor.event {signal, duration_s, detail}` — an observation, never a score. |
| The server owns validation | Signals are checked against a closed server-side whitelist; unknown values are rejected. Detail payloads are sanitized before persisting. |
| The server owns scoring | Points and the meeting minute are computed server-side from `PROCTOR_SIGNALS` (`app/models/proctor.py`); a client cannot inflate or forge a score. |
| Abuse is bounded | WS gateway rate limit: 30 proctor events/min per (user, meeting). |
| The host is exempt | Host connections never generate events, and proctor frames from a host connection are ignored. |
| Flags are host-only | `proctor.flag` frames are filtered at relay level (`_deliverable`), the same pattern as host-only notes — non-hosts never receive them. |
| The report is host-only | `GET /meetings/{code}/report` and `.csv` re-derive the caller's host role server-side. |
| Exam meetings require a password | Server-side schema validation rejects exam creation without a password of 8+ chars. |
| Evidence clips are server-validated | A clip must reference the uploader's **own** event in the same exam (verified server-side); a partial unique index allows one active clip per event; the report carries the honest clip status (`uploaded`/`failed`/`missing`). |

Known limit: on-device detection can be evaded by a determined student (covering the
camera, a second device). The design keeps the *score* trustworthy regardless; it does
not claim to make cheating impossible.

## 7. Explicitly out of scope (current phases)

LLM processing / AI meeting assistance — future phases, **not** implemented or stubbed
with real logic. Client-side proctoring with server-authoritative scoring shipped in
Phase 16 (§6) and is no longer out of scope.
