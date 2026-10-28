"""Stored-object metadata (Phase 17 — object storage, DECISIONS.md D24).

PostgreSQL is the source of truth for file metadata and permissions; the object
store holds only bytes under a private key. Rows reference storage *keys*, never
provider URLs, so the provider (MinIO vs Cloudflare R2) can be swapped without
touching application data.

Lifecycle of ``upload_status``:

    pending  → upload started, bytes not yet confirmed
    uploaded → bytes present in the object store
    failed   → upload attempted and failed (report shows the gap honestly)
    missing  → a read found the object gone (drift between DB and store)
    deleted  → tombstoned by owner/host; object deletion attempted
    purged   → object confirmed gone (tombstone remains for the audit trail)

``legal_hold`` freezes a file out of retention cleanup — active reviews,
appeals, and preservation requests must never lose evidence (D24 §6).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Closed sets — enforced in the DB so a bad write can never violate them.
FILE_PURPOSES = ("evidence_clip", "screenshot", "attachment")
UPLOAD_STATUSES = ("pending", "uploaded", "failed", "missing", "deleted", "purged")


class StoredFile(Base):
    """One uploaded object (evidence clip, screenshot, or attachment)."""

    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('evidence_clip', 'screenshot', 'attachment')",
            name="ck_stored_files_purpose",
        ),
        CheckConstraint(
            "upload_status IN ('pending', 'uploaded', 'failed', 'missing', 'deleted', 'purged')",
            name="ck_stored_files_upload_status",
        ),
        Index("ix_stored_files_meeting_id_created_at", "meeting_id", "created_at"),
        Index("ix_stored_files_retention_expires_at", "retention_expires_at"),
        # At most one *active* clip per proctoring event (retries reuse the row;
        # a soft-deleted row releases the slot for a fresh upload).
        Index(
            "uq_stored_files_proctor_event_active",
            "proctor_event_id",
            unique=True,
            postgresql_where="proctor_event_id IS NOT NULL AND deleted_at IS NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Uploader (student for clips/screenshots, host for their documentation).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The proctoring event this evidence clip substantiates (clips only).
    proctor_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proctor_events.id", ondelete="SET NULL"),
    )
    #: Provider-private object key — never a URL (D24 §5).
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    #: Which provider wrote the bytes ("minio" / "r2") — migration diagnostics.
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(96), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Sanitized original filename (display only — never used for the key).
    original_name: Mapped[str | None] = mapped_column(String(255))
    upload_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    #: Preservation freeze: blocks retention cleanup and manual deletion.
    legal_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: When automatic retention may remove this object (NULL = keep forever).
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Tombstone (soft delete); ``upload_status`` records the object outcome.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
