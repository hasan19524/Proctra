"""Notes persistence and wire DTOs (Phase 7).

The gateway validates membership/visibility/size, calls ``upsert_note``, and
broadcasts the returned DTO — same shape as chat: the DB is the source of
truth, ``sync.state`` re-seeds late joiners.
"""

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import VISIBILITIES, VISIBILITY_HOST_ONLY, MeetingNote
from app.models.user import User


def note_dto(note: MeetingNote, updated_by_name: str | None) -> dict[str, Any]:
    """Wire representation of one persisted notes document."""
    return {
        "id": str(note.id),
        "meeting_id": str(note.meeting_id),
        "visibility": note.visibility,
        "content": note.content,
        "updated_by": str(note.updated_by) if note.updated_by else None,
        "updated_by_name": updated_by_name,
        "updated_at": note.updated_at.isoformat(),
    }


async def upsert_note(
    session: AsyncSession,
    *,
    meeting_id: UUID,
    visibility: str,
    content: dict[str, Any],
    updated_by: UUID,
) -> MeetingNote:
    """Insert or replace the notes document for ``(meeting_id, visibility)``."""
    if visibility not in VISIBILITIES:
        raise ValueError(f"unknown visibility: {visibility}")
    note = await session.scalar(
        select(MeetingNote).where(
            MeetingNote.meeting_id == meeting_id, MeetingNote.visibility == visibility
        )
    )
    if note is None:
        note = MeetingNote(
            id=uuid.uuid4(),
            meeting_id=meeting_id,
            visibility=visibility,
            content=content,
            updated_by=updated_by,
        )
        session.add(note)
    else:
        note.content = content
        note.updated_by = updated_by
    await session.commit()
    return note


async def list_notes(
    session: AsyncSession,
    meeting_id: UUID,
    *,
    include_host_only: bool,
) -> list[tuple[MeetingNote, str | None]]:
    """Notes for a meeting with the editor's display name.

    ``host_only`` documents are omitted unless the caller is the host.
    """
    rows = await session.execute(
        select(MeetingNote, User.display_name)
        .join(User, User.id == MeetingNote.updated_by, isouter=True)
        .where(MeetingNote.meeting_id == meeting_id)
        .order_by(MeetingNote.visibility)
    )
    notes: list[tuple[MeetingNote, str | None]] = [(note, name) for note, name in rows.all()]
    if include_host_only:
        return notes
    return [(note, name) for note, name in notes if note.visibility != VISIBILITY_HOST_ONLY]
