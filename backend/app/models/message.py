"""Chat message model (Phase 5).

Durable per-meeting chat: every message carries the Redis-allocated ``seq``
used for reconnect replay (REALTIME.md §3).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MAX_BODY_LENGTH = 4000
MAX_CLIENT_ID_LENGTH = 64


class Message(Base):
    """One persisted chat message inside a meeting."""

    __tablename__ = "meeting_messages"
    __table_args__ = (
        Index("ix_meeting_messages_meeting_seq", "meeting_id", "seq"),
        Index(
            "uq_meeting_messages_client",
            "meeting_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(MAX_CLIENT_ID_LENGTH))
    reply_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_messages.id", ondelete="SET NULL"),
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
