"""Participant attendance helpers (Phase 6).

Write-only history: join inserts a row, the last disconnect stamps ``left_at``.
Nothing here authorizes anything — authorization stays in the gateway/DB.
"""

from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import MeetingParticipant


async def record_join(
    session: AsyncSession,
    *,
    meeting_id: UUID,
    user_id: UUID,
    role: str,
) -> None:
    """Open an attendance row for one join session."""
    session.add(MeetingParticipant(meeting_id=meeting_id, user_id=user_id, role=role))
    await session.commit()


async def record_leave(session: AsyncSession, *, meeting_id: UUID, user_id: UUID) -> None:
    """Stamp ``left_at`` on any still-open rows for this user."""
    await session.execute(
        update(MeetingParticipant)
        .where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.user_id == user_id,
            MeetingParticipant.left_at.is_(None),
        )
        .values(left_at=func.now())
    )
    await session.commit()
