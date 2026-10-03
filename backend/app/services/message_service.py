"""Chat message persistence and wire DTOs (Phase 5).

The gateway stays thin: it validates, allocates ``seq``, calls the service and
broadcasts the returned DTO. Replay reads come from Postgres, never Redis
(REALTIME.md §3 — chat survives transient network loss).
"""

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MAX_CLIENT_ID_LENGTH, Message
from app.models.user import User


def message_dto(message: Message, sender_name: str) -> dict[str, Any]:
    """Wire representation of one persisted message (``chat.message`` payload)."""
    return {
        "id": str(message.id),
        "meeting_id": str(message.meeting_id),
        "sender_id": str(message.sender_id),
        "sender_name": sender_name,
        "body": message.body,
        "client_id": message.client_id,
        "reply_to": str(message.reply_to) if message.reply_to else None,
        "seq": message.seq,
        "created_at": message.created_at.isoformat(),
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
    }


async def create_message(
    session: AsyncSession,
    *,
    meeting_id: UUID,
    sender_id: UUID,
    sender_name: str,
    body: str,
    seq: int,
    client_id: str | None = None,
    reply_to: UUID | None = None,
) -> tuple[Message, bool]:
    """Persist a message; returns ``(message, created)``.

    ``client_id`` is the client's idempotency key: a retry with the same key
    returns the already-persisted row instead of duplicating it.
    """
    if client_id and len(client_id) > MAX_CLIENT_ID_LENGTH:
        client_id = client_id[:MAX_CLIENT_ID_LENGTH]
    message = Message(
        meeting_id=meeting_id,
        sender_id=sender_id,
        body=body,
        seq=seq,
        client_id=client_id,
        reply_to=reply_to,
    )
    session.add(message)
    try:
        await session.commit()
        return message, True
    except IntegrityError:
        await session.rollback()
        if not client_id:
            raise
        existing = await session.scalar(
            select(Message).where(
                Message.meeting_id == meeting_id,
                Message.client_id == client_id,
            )
        )
        if existing is None:
            raise
        return existing, False


async def get_by_client_id(
    session: AsyncSession, meeting_id: UUID, client_id: str
) -> Message | None:
    """Fetch a message by its idempotency key."""
    return await session.scalar(
        select(Message).where(
            Message.meeting_id == meeting_id,
            Message.client_id == client_id,
        )
    )


async def list_messages_after(
    session: AsyncSession,
    meeting_id: UUID,
    after_seq: int,
    *,
    limit: int = 500,
) -> list[tuple[Message, str]]:
    """Messages with ``seq > after_seq``, oldest first (reconnect replay)."""
    rows = await session.execute(
        select(Message, User.display_name)
        .join(User, User.id == Message.sender_id)
        .where(
            Message.meeting_id == meeting_id, Message.seq > after_seq, Message.deleted_at.is_(None)
        )
        .order_by(Message.seq)
        .limit(limit)
    )
    return [(message, name) for message, name in rows.all()]


async def list_recent_messages(
    session: AsyncSession,
    meeting_id: UUID,
    *,
    limit: int = 50,
) -> list[tuple[Message, str]]:
    """The newest ``limit`` messages, oldest first (snapshot chat tail)."""
    rows = await session.execute(
        select(Message, User.display_name)
        .join(User, User.id == Message.sender_id)
        .where(Message.meeting_id == meeting_id, Message.deleted_at.is_(None))
        .order_by(Message.seq.desc())
        .limit(limit)
    )
    return [(message, name) for message, name in reversed(rows.all())]


def random_client_id() -> str:
    """Fallback idempotency key when the client sends none."""
    return uuid.uuid4().hex[:MAX_CLIENT_ID_LENGTH]
