"""Meeting routes (Phases 3, 9)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from livekit import api as livekit_api
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db import get_session
from app.models.user import User
from app.schemas.meeting import CreateMeetingRequest, LiveKitTokenOut, MeetingOut
from app.services import meeting_service
from app.services.meeting_service import MeetingNotFoundError

router = APIRouter(prefix="/meetings", tags=["meetings"])

# Long enough for a call, short enough to limit leaked-token replay.
LIVEKIT_TOKEN_TTL = timedelta(minutes=10)


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: CreateMeetingRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Start a new meeting hosted by the current user."""
    meeting = await meeting_service.create_meeting(session, user.id, title=payload.title)
    await session.commit()
    return MeetingOut.model_validate(meeting)


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
    return MeetingOut.model_validate(meeting)


@router.post("/{code}/token", response_model=LiveKitTokenOut)
async def mint_livekit_token(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LiveKitTokenOut:
    """Mint SFU credentials — only after the same lock/end checks as the WS.

    ARCHITECTURE.md §8: FastAPI is the single authority that decides who may
    join media; LiveKit never makes that decision itself.
    """
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
