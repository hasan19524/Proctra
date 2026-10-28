"""Invite roster for exam meetings (Phase 16 — exam mode).

The expected-student list the proctor's report is graded against: an invitee
who never shows up is ABSENT, anyone who joined is PRESENT. Standard meetings
have no roster and skip this table entirely.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MeetingInvite(Base):
    """One expected attendee email on a meeting's invite roster."""

    __tablename__ = "meeting_invites"
    __table_args__ = (
        UniqueConstraint("meeting_id", "email", name="uq_meeting_invites_meeting_email"),
        Index("ix_meeting_invites_meeting_id", "meeting_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
