"""Proctoring signal model (Phase 16 — exam mode).

One row per observed cheating signal. The vision model runs in the student's
browser (MediaPipe face landmarker on their own camera — no video ever leaves
the device); the client emits *observations* over the app WebSocket and the
server is the single authority that validates them, assigns points, stamps the
meeting minute, persists the row, and fans the flag out to the host. A client
never supplies its own score (SECURITY.md §5 — validate everything).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Signal type -> points added to the student's cheating score. Server-owned.
PROCTOR_SIGNALS: dict[str, int] = {
    # Eyes or head off the screen for a sustained period — the classic
    # "looking around" flag (+2, per the product spec).
    "looking_away": 2,
    # No face in frame for a sustained period (camera covered / left desk).
    "no_face": 3,
    # A second person visible in the frame.
    "multiple_faces": 5,
    # Mouth moving / talking during the exam.
    "speaking": 1,
    # Eyes closed for a sustained period (dozing / reading something below).
    "eyes_closed": 1,
    # Exam tab lost focus — switched to another application.
    "tab_hidden": 2,
    # Video quality issue: a coverage gap for the proctor, never scored.
    "video_blur": 0,
}

# Human labels for the host-facing flag feed and the CSV report.
PROCTOR_LABELS: dict[str, str] = {
    "looking_away": "looking away",
    "no_face": "no face in frame",
    "multiple_faces": "second person in frame",
    "speaking": "speaking",
    "eyes_closed": "eyes closed",
    "tab_hidden": "left the exam tab",
    "video_blur": "blurry video",
}

SIGNAL_TYPES = frozenset(PROCTOR_SIGNALS)

# Bound the client-supplied observation detail (echoed to the host).
MAX_DETAIL_CHARS = 400
# Clamp for the observed duration of one signal episode.
MAX_DURATION_SECONDS = 600.0


class ProctorEvent(Base):
    """One scored proctoring observation inside an exam meeting."""

    __tablename__ = "proctor_events"
    __table_args__ = (
        CheckConstraint(
            f"signal IN ({', '.join(repr(s) for s in sorted(SIGNAL_TYPES))})",
            name="ck_proctor_events_signal",
        ),
        Index("ix_proctor_events_meeting_id_created_at", "meeting_id", "created_at"),
        Index("ix_proctor_events_meeting_id_user_id", "meeting_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The student the observation is about (always the sender; never client-set).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal: Mapped[str] = mapped_column(String(24), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    # Minutes elapsed since the meeting opened (started_at, else created_at).
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(nullable=False, default=0.0)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
