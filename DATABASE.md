# Procto — Database

PostgreSQL 16 is the source of truth for **durable state only**.

## Conventions

- UUID primary keys (`gen_random_uuid()`, `pgcrypto`) for domain tables.
- Timestamps: `TIMESTAMPTZ`, always UTC, columns named `created_at` / `updated_at`.
- Booleans for flags, explicit `NOT NULL` on required columns.
- Foreign keys with explicit `ON DELETE` behaviour.
- Soft history (`left_at`) for meeting participation rather than deleting rows.
- Plural snake_case table names.
- **Alembic owns the schema** — never hand-edit the database; every schema change is a
  migration.
- Migrations live in `backend/alembic/versions/`.

## Phase 0

Only the migration infrastructure exists (empty initial revision) so every later phase
ships its tables as a real migration.

## Planned tables (by phase)

### Phase 2 — Authentication

```text
users
  id             UUID PK
  email          CITEXT UNIQUE NOT NULL
  password_hash  TEXT NOT NULL            -- argon2id
  display_name   TEXT NOT NULL
  avatar_url     TEXT NULL
  role           TEXT NOT NULL DEFAULT 'user'
                 CHECK (role IN ('user','host'))
  is_active      BOOLEAN NOT NULL DEFAULT TRUE
  created_at     TIMESTAMPTZ NOT NULL
  updated_at     TIMESTAMPTZ NOT NULL

refresh_tokens
  id             UUID PK
  user_id        UUID FK -> users ON DELETE CASCADE
  token_hash     TEXT NOT NULL UNIQUE    -- sha256 of the opaque token
  expires_at     TIMESTAMPTZ NOT NULL
  revoked_at     TIMESTAMPTZ NULL
  created_at     TIMESTAMPTZ NOT NULL
```

### Phase 4 — Meetings

```text
meetings
  id                        UUID PK
  meeting_id                TEXT UNIQUE NOT NULL  -- human shareable code abc-def-ghi
  title                     TEXT NOT NULL
  description               TEXT NULL
  password_hash             TEXT NULL
  host_id                   UUID FK -> users
  waiting_room_enabled      BOOLEAN NOT NULL DEFAULT TRUE
  locked                    BOOLEAN NOT NULL DEFAULT FALSE
  allow_chat                BOOLEAN NOT NULL DEFAULT TRUE
  allow_screen_share        BOOLEAN NOT NULL DEFAULT TRUE
  allow_reactions           BOOLEAN NOT NULL DEFAULT TRUE
  started_at                TIMESTAMPTZ NULL
  ended_at                  TIMESTAMPTZ NULL
  created_at                TIMESTAMPTZ NOT NULL
```

### Phase 5/6 — Participants

```text
meeting_participants
  id             UUID PK
  meeting_id     UUID FK -> meetings ON DELETE CASCADE
  user_id        UUID FK -> users NULL     -- guests may be NULL
  guest_name     TEXT NULL
  role           TEXT NOT NULL             -- host | co_host | participant
  joined_at      TIMESTAMPTZ NOT NULL
  left_at        TIMESTAMPTZ NULL
```

### Phase 9 — Chat

```text
meeting_messages
  id             UUID PK
  meeting_id     UUID FK -> meetings ON DELETE CASCADE
  sender_id      UUID FK -> users
  recipient_id   UUID FK -> users NULL     -- NULL = public, set = private
  reply_to_id    UUID FK -> meeting_messages NULL
  body           TEXT NOT NULL
  attachment_url TEXT NULL
  seq            BIGINT NOT NULL           -- per-meeting monotonic, drives reconnect sync
  created_at     TIMESTAMPTZ NOT NULL
  deleted_at     TIMESTAMPTZ NULL
```

### Phase 12 — Notes

```text
meeting_notes
  id             UUID PK
  meeting_id     UUID FK -> meetings ON DELETE CASCADE
  content        JSONB NOT NULL            -- rich text document
  visibility     TEXT NOT NULL DEFAULT 'all'   -- all | host_only
  updated_by     UUID FK -> users
  updated_at     TIMESTAMPTZ NOT NULL
  UNIQUE (meeting_id, visibility)
```

### Phase 13 — Security / audit

```text
audit_logs
  id             UUID PK
  actor_id       UUID NULL
  meeting_id     UUID NULL
  action         TEXT NOT NULL             -- meeting.lock, participant.remove, ...
  target_id      UUID NULL
  metadata       JSONB NOT NULL DEFAULT '{}'
  created_at     TIMESTAMPTZ NOT NULL
```

### Phase 15 — History

```text
meeting_history  (or derived views over meetings + meeting_participants)
  duration, participant_count, status derived from meetings/attendance rows
```

### Phase 17 — Exam/Interview (future)

```text
exams, exam_enrollments, exam_sessions   -- reuses meetings table + Meeting Core
```

## Indexes (planned)

- `users.email` (unique), `refresh_tokens.token_hash` (unique)
- `meetings.meeting_id` (unique)
- `meeting_messages (meeting_id, seq)` — ordering + reconnect replay
- `meeting_participants (meeting_id, joined_at)` — attendance queries
- `audit_logs (meeting_id, created_at)`

## Redis keyspace

```text
ws:meeting:{meeting_id}        pub/sub channel for app WS fan-out
ratelimit:{bucket}:{key}       sliding-window counters with TTL
```

No durable business data in Redis.
