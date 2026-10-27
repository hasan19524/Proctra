"""Meeting routes (Phases 3, 9, 13)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from livekit import api as livekit_api
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.ratelimit import rate_limit
from app.core.security import verify_password
from app.db import get_session
from app.models.meeting import Meeting
from app.models.user import User
from app.schemas.meeting import (
    CreateMeetingRequest,
    LiveKitTokenOut,
    LiveKitTokenRequest,
    MeetingOut,
)
from app.services import meeting_service
from app.services.meeting_service import MeetingNotFoundError
from app.ws.waiting import APPROVED, get_decision

router = APIRouter(prefix="/meetings", tags=["meetings"])

# Long enough for a call, short enough to limit leaked-token replay.
LIVEKIT_TOKEN_TTL = timedelta(minutes=10)
# Mint budget per user per minute: a call re-mints on reconnect (D22) but a
# brute-force loop cannot spin on it (SECURITY.md §4).
TOKEN_MINT_RATE = (60, 60)


def _meeting_out(meeting: Meeting) -> MeetingOut:
    """Serialize without ever exposing ``password_hash`` (SECURITY.md §4)."""
    out = MeetingOut.model_validate(meeting)
    out.has_password = meeting.password_hash is not None
    return out


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: CreateMeetingRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Start a new meeting hosted by the current user."""
    meeting = await meeting_service.create_meeting(
        session,
        user.id,
        title=payload.title,
        password=payload.password,
        waiting_room=payload.waiting_room,
    )
    await session.commit()
    return _meeting_out(meeting)


@router.get("/{code}", response_model=MeetingOut)
async def get_meeting(
    code: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Look up a meeting by join code (used by the pre-join lobby)."""
    try:
        meeting = await meeting_service.get_meeting_by_code(session, code)
    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        ) from exc
    return _meeting_out(meeting)


@router.post("/{code}/token", response_model=LiveKitTokenOut)
async def mint_livekit_token(
    code: str,
    payload: LiveKitTokenRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LiveKitTokenOut:
    """Mint SFU credentials — only after the same lock/end/password/waiting
    checks as the WS (ARCHITECTURE.md §8: FastAPI is the single authority
    that decides who may join media).
    """
    await rate_limit("meeting_token", str(user.id), *TOKEN_MINT_RATE)

    try:
        meeting = await meeting_service.get_meeting_by_code(session, code)
    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        ) from exc

    if meeting.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Meeting has ended",
        )
    is_host = str(meeting.host_id) == str(user.id)
    if meeting.is_locked and not is_host:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Meeting is locked",
        )
    if meeting.password_hash is not None and not is_host:
        password = payload.password if payload else None
        if not password or not verify_password(password, meeting.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Meeting password required",
            )
    if (
        meeting.waiting_room
        and not is_host
        and await get_decision(meeting.code, str(user.id)) != APPROVED
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Waiting for host approval",
        )

    token = (
        livekit_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(str(user.id))
        .with_name(user.display_name)
        .with_ttl(LIVEKIT_TOKEN_TTL)
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=meeting.code,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )
    return LiveKitTokenOut(url=settings.livekit_url, token=token.to_jwt())
