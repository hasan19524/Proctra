"""Meeting routes (Phase 3)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db import get_session
from app.models.user import User
from app.schemas.meeting import CreateMeetingRequest, MeetingOut
from app.services import meeting_service
from app.services.meeting_service import MeetingNotFoundError

router = APIRouter(prefix="/meetings", tags=["meetings"])


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
