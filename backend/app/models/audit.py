"""Audit log for security-relevant meeting actions (SECURITY.md 3, Phase 13).

Append-only: who did what to whom inside a meeting (lock, end, remove,
permission changes, waiting-room decisions). Never holds message/note content.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# The security-relevant verbs (SECURITY.md 3); keep the set closed.
AUDIT_ACTIONS = frozenset(
    {
        "lock",
        "unlock",
        "end",
        "mute_participant",
        "remove",
        "set_permissions",
        "waiting_approve",
        "waiting_reject",
    }
)


class AuditLog(Base):
    """One security-relevant action taken by a host inside a meeting."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_meeting_id_created_at", "meeting_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
