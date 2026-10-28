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

### Phase 16 — Exam mode & proctoring

Migration `0f3c9d1a2b4e` (phase_16_exam_mode_proctoring).

`meetings` gains two columns:

```text
kind                  TEXT NOT NULL DEFAULT 'standard'
                      CHECK (kind IN ('standard','exam'))
proctoring_enabled    BOOLEAN NOT NULL DEFAULT FALSE
```

```text
meeting_invites  (expected-student roster the integrity report is graded against)
  id             UUID PK
  meeting_id     UUID FK -> meetings ON DELETE CASCADE
  email          CITEXT NOT NULL
  created_at     TIMESTAMPTZ NOT NULL
  UNIQUE (meeting_id, email)

proctor_events
  id             UUID PK
  meeting_id     UUID FK -> meetings ON DELETE CASCADE
  user_id        UUID FK -> users ON DELETE CASCADE
  signal         VARCHAR(24) NOT NULL
                 CHECK (signal IN ('looking_away','no_face','multiple_faces',
                                   'speaking','eyes_closed','tab_hidden','video_blur'))
  points         INTEGER NOT NULL           -- server-computed; video_blur always 0
  minute         INTEGER NOT NULL           -- minutes since meeting opened
  duration_s     FLOAT NULL
  detail         JSONB NULL
  created_at     TIMESTAMPTZ NOT NULL
```

### Phase 17 — Object storage (stored_files)

Migration `b7e2a91c40d3` (phase_17_object_storage). Bytes live in MinIO/R2
(D24); Postgres owns metadata, permissions, and retention:

```text
stored_files
  id                    UUID PK
  meeting_id            UUID FK -> meetings ON DELETE CASCADE
  user_id               UUID FK -> users ON DELETE CASCADE      -- uploader
  proctor_event_id      UUID FK -> proctor_events ON DELETE SET NULL
  storage_key           VARCHAR(512) NOT NULL UNIQUE   -- private key, never a URL
  provider              VARCHAR(16) NOT NULL           -- 'minio' | 'r2'
  purpose               VARCHAR(24) NOT NULL
                        CHECK (purpose IN ('evidence_clip','screenshot','attachment'))
  mime_type             VARCHAR(96) NOT NULL           -- sniffed from magic bytes
  file_size             BIGINT NOT NULL
  original_name         VARCHAR(255) NULL
  upload_status         VARCHAR(16) NOT NULL DEFAULT 'pending'
                        CHECK (upload_status IN ('pending','uploaded','failed',
                                                 'missing','deleted','purged'))
  legal_hold            BOOLEAN NOT NULL DEFAULT FALSE  -- freezes retention/cleanup
  retention_expires_at  TIMESTAMPTZ NULL                -- NULL = keep forever
  created_at            TIMESTAMPTZ NOT NULL
  deleted_at            TIMESTAMPTZ NULL                -- tombstone

  INDEX (meeting_id, created_at)
  INDEX (retention_expires_at)                 -- retention sweep
  UNIQUE (proctor_event_id) WHERE proctor_event_id IS NOT NULL
                              AND deleted_at IS NULL      -- one active clip per event
```

## Indexes (planned)

- `users.email` (unique), `refresh_tokens.token_hash` (unique)
- `meetings.meeting_id` (unique)
- `meeting_messages (meeting_id, seq)` — ordering + reconnect replay
- `meeting_participants (meeting_id, joined_at)` — attendance queries
- `audit_logs (meeting_id, created_at)`
- `meeting_invites (meeting_id, email)` (unique)
- `proctor_events (meeting_id, created_at)`, `proctor_events (meeting_id, user_id)` — report queries
- `stored_files (meeting_id, created_at)`, `stored_files (retention_expires_at)`,
  partial-unique `stored_files (proctor_event_id) WHERE proctor_event_id IS NOT NULL AND deleted_at IS NULL`

## Redis keyspace

```text
ws:meeting:{meeting_id}        pub/sub channel for app WS fan-out
ratelimit:{bucket}:{key}       sliding-window counters with TTL
```

No durable business data in Redis.
