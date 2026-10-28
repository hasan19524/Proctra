"""Meeting lifecycle helpers (Phase 3)."""

import re
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.meeting import Meeting

# Unambiguous alphabet (no 0/o/1/l) and Meet-style three groups of three.
CODE_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
CODE_GROUP = 3
CODE_GROUPS = 3
CODE_RE = re.compile(r"^[a-z2-9]{3}-[a-z2-9]{3}-[a-z2-9]{3}$")
CODE_ATTEMPTS = 5


class MeetingNotFoundError(Exception):
    """Raised when no meeting exists for the given code."""


def generate_code() -> str:
    """Generate a human-friendly join code like ``ktq-vxm-pnz``."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP * CODE_GROUPS))
    groups = [raw[i : i + CODE_GROUP] for i in range(0, len(raw), CODE_GROUP)]
    return "-".join(groups)


def normalize_code(code: str) -> str:
    """Trim and lowercase a code pasted by a user."""
    return code.strip().lower()


async def create_meeting(
    session: AsyncSession,
    host_id: UUID,
    title: str | None = None,
    password: str | None = None,
    waiting_room: bool = False,
    kind: str = "standard",
    proctoring_enabled: bool = False,
    invite_emails: list[str] | None = None,
) -> Meeting:
    """Create a meeting owned by ``host_id``, retrying on code collisions.

    ``password`` is hashed (Argon2id, SECURITY.md §1) before it touches the
    database; the plain value never leaves this function. ``invite_emails``
    seeds the roster the exam report's present/absent columns are graded
    against (Phase 16); duplicates are silently dropped.
    """
    from app.models.invite import MeetingInvite

    for attempt in range(CODE_ATTEMPTS):
        meeting = Meeting(
            code=generate_code(),
            title=title,
            host_id=host_id,
            password_hash=hash_password(password) if password else None,
            waiting_room=waiting_room,
            kind=kind,
            proctoring_enabled=proctoring_enabled if kind == "exam" else False,
        )
        session.add(meeting)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            if attempt == CODE_ATTEMPTS - 1:
                raise
            continue

        # Seed the invite roster (best-effort; the meeting itself is safe).
        if invite_emails:
            seen: set[str] = set()
            for email in invite_emails:
                normalized = email.strip().lower()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                session.add(MeetingInvite(meeting_id=meeting.id, email=normalized))
            await session.flush()
        return meeting
    raise RuntimeError("unreachable")  # pragma: no cover


async def get_meeting_by_code(session: AsyncSession, code: str) -> Meeting:
    """Look a meeting up by (normalized) code or raise ``MeetingNotFoundError``."""
    normalized = normalize_code(code)
    meeting = await session.scalar(select(Meeting).where(Meeting.code == normalized))
    if meeting is None:
        raise MeetingNotFoundError(normalized)
    return meeting


async def list_user_meetings(
    session: AsyncSession, user_id: UUID, limit: int = 20
) -> list[Meeting]:
    """List meetings the user hosted or participated in (Phase 14)."""
    from app.models.participant import MeetingParticipant

    stmt = (
        select(Meeting)
        .join(
            MeetingParticipant,
            MeetingParticipant.meeting_id == Meeting.id,
            isouter=True,
        )
        .where((Meeting.host_id == user_id) | (MeetingParticipant.user_id == user_id))
        .distinct()
        .order_by(Meeting.created_at.desc())
        .limit(limit)
    )
    result = await session.scalars(stmt)
    return list(result.all())
