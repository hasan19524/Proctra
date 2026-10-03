"""Shared meeting notes (Phase 7).

One row per ``(meeting_id, visibility)`` — a whole-document store, not a
message log: every save replaces ``content``. ``visibility='host_only'`` is
the host's private document and is filtered out of snapshots for everyone
else (SECURITY.md — no cross-visibility reads).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VISIBILITY_ALL = "all"
VISIBILITY_HOST_ONLY = "host_only"
VISIBILITIES = (VISIBILITY_ALL, VISIBILITY_HOST_ONLY)

MAX_NOTE_CONTENT_CHARS = 100_000


class MeetingNote(Base):
    """A shared (or host-only) notes document for one meeting."""

    __tablename__ = "meeting_notes"
    __table_args__ = (
        CheckConstraint("visibility IN ('all', 'host_only')", name="ck_meeting_notes_visibility"),
        UniqueConstraint("meeting_id", "visibility", name="uq_meeting_notes_meeting_visibility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default=VISIBILITY_ALL)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
