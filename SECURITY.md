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
- File uploads (Phase 9): size limits, extension/content-type allow-list, stored
  outside the web root with randomized names.
- Errors returned to clients are generic; detail goes to structured server logs.

## 6. Explicitly out of scope (current phases)

AI/ML systems, proctoring/cheating detection, computer vision, LLM processing — these
are future phases and are **not** implemented or stubbed with real logic.
