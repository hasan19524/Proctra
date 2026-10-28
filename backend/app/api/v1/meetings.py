"""Meeting routes (Phases 3, 9, 13, 16 — exam mode + proctor report)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    MeetingHistoryOut,
    MeetingOut,
    ReportOut,
)
from app.services import meeting_service, proctor_service
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


@router.get("/history", response_model=list[MeetingHistoryOut])
async def get_meeting_history(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
) -> list[MeetingHistoryOut]:
    """List meetings the current user hosted or joined (Phase 14)."""
    if limit < 1 or limit > 50:
        limit = 20
    meetings = await meeting_service.list_user_meetings(session, user.id, limit=limit)
    return [MeetingHistoryOut.model_validate(m) for m in meetings]


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: CreateMeetingRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Start a new meeting hosted by the current user.

    Phase 16: ``kind="exam"`` creates a proctored exam room (requires a
    password; seeds the invite roster the report is graded against).
    """
    await rate_limit("meeting_create", str(user.id), 20, 60)
    meeting = await meeting_service.create_meeting(
        session,
        user.id,
        title=payload.title,
        password=payload.password,
        waiting_room=payload.waiting_room,
        kind=payload.kind,
        proctoring_enabled=payload.proctoring_enabled if payload.kind == "exam" else False,
        invite_emails=payload.invite_emails,
    )
    await session.commit()
    return _meeting_out(meeting)


@router.get("/{code}", response_model=MeetingOut)
async def get_meeting(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Look up a meeting by join code (used by the pre-join lobby)."""
    # Bounds code enumeration: a single account cannot spray many codes.
    await rate_limit("meeting_lookup", str(user.id), 60, 60)
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


async def _require_host_report(code: str, user: User, session: AsyncSession) -> Meeting:
    """Load a meeting and assert the caller is its host (report gate)."""
    try:
        meeting = await meeting_service.get_meeting_by_code(session, code)
    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        ) from exc
    if str(meeting.host_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can access the report",
        )
    return meeting


@router.get("/{code}/report", response_model=ReportOut)
async def get_exam_report(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    """Full exam report: roster (present/absent) + per-student scores + events.

    Host-only. Returns JSON for the UI's live integrity panel; use
    ``GET /{code}/report.csv`` for the downloadable file.
    """
    await rate_limit("report_fetch", str(user.id), 30, 60)
    meeting = await _require_host_report(code, user, session)
    return await proctor_service.build_report(session, meeting)


@router.get("/{code}/report.csv")
async def download_exam_report_csv(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download the exam report as a CSV file the proctor can open in Excel."""
    await rate_limit("report_fetch", str(user.id), 30, 60)
    meeting = await _require_host_report(code, user, session)
    report = await proctor_service.build_report(session, meeting)
    csv_text = proctor_service.report_to_csv(report)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="procto-report-{meeting.code}.csv"'},
    )
