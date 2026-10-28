"""Meeting model (Phases 3, 16 — exam mode)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Meeting kinds: a standard Google-Meet-style room, or a proctored exam room.
KIND_STANDARD = "standard"
KIND_EXAM = "exam"
MEETING_KINDS = (KIND_STANDARD, KIND_EXAM)


class Meeting(Base):
    """A Procto meeting room, addressable by its short join code."""

    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("status IN ('waiting', 'live', 'ended')", name="ck_meetings_status"),
        CheckConstraint("kind IN ('standard', 'exam')", name="ck_meetings_kind"),
        Index("ix_meetings_host_id", "host_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(11), unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(120))
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting")
    # Phase 16: "standard" (regular meet) or "exam" (proctored examination).
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=KIND_STANDARD)
    is_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    allow_chat: Mapped[bool] = mapped_column(nullable=False, default=True)
    allow_reactions: Mapped[bool] = mapped_column(nullable=False, default=True)
    allow_screen_share: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Phase 13: optional Argon2id join password (never returned to clients -
    # exposure is the `has_password` flag on the API schema).
    password_hash: Mapped[str | None] = mapped_column(String(200))
    waiting_room: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Phase 16: whether the vision model is actively proctoring this exam.
    proctoring_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
