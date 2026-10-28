"""Exam-mode helpers: validate proctor observations, build the report (Phase 16).

The vision model runs in each student's browser (MediaPipe face landmarker on
their own camera — no video ever leaves the device). The client emits
*observations* over the app WebSocket; this service is the single authority
that validates them, assigns points, stamps the meeting minute, persists the
row, and (via the gateway) fans the flag out to the host. A client never
supplies its own score (SECURITY.md §5 — validate everything).
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import StoredFile
from app.models.invite import MeetingInvite
from app.models.meeting import Meeting
from app.models.participant import MeetingParticipant
from app.models.proctor import (
    MAX_DETAIL_CHARS,
    MAX_DURATION_SECONDS,
    PROCTOR_LABELS,
    PROCTOR_SIGNALS,
    SIGNAL_TYPES,
    ProctorEvent,
)
from app.models.user import User
from app.schemas.meeting import (
    ProctorFlagOut,
    ProctorStudentOut,
    ReportOut,
    ReportStudentOut,
)


def meeting_clock_start(meeting: Meeting) -> datetime:
    """The t0 the report's timeline is measured against."""
    return meeting.started_at or meeting.created_at


def compute_minute(meeting: Meeting, at: datetime | None = None) -> int:
    """Minutes elapsed since the meeting opened (clamped at 0)."""
    at = at or datetime.now(UTC)
    t0 = meeting_clock_start(meeting)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=UTC)
    elapsed = (at - t0).total_seconds()
    return max(0, int(elapsed // 60))


def sanitize_detail(detail: dict[str, object] | None) -> dict[str, object] | None:
    """Clamp client-supplied observation detail (echoed to the host, stored).

    Keeps only JSON-safe scalars under a size cap so a hostile client cannot
    bloat the row or smuggle markup into the host's panel.
    """
    if not detail:
        return None
    cleaned: dict[str, object] = {}
    for key, value in list(detail.items())[:12]:
        if not isinstance(key, str) or not key.isidentifier():
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            cleaned[key[:40]] = value
        elif isinstance(value, str):
            cleaned[key[:40]] = value[:MAX_DETAIL_CHARS]
    return cleaned or None


def clamp_duration(duration_s: object) -> float:
    """Clamp a client-supplied duration into [0, MAX_DURATION_SECONDS]."""
    try:
        value = float(duration_s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(value, MAX_DURATION_SECONDS))


async def record_event(
    session: AsyncSession,
    *,
    meeting: Meeting,
    user: User,
    signal: str,
    duration_s: float = 0.0,
    detail: dict[str, object] | None = None,
) -> ProctorEvent:
    """Validate + persist one proctoring observation; returns the stored row.

    The signal must be in the closed set; points and minute are computed
    server-side and never taken from the client.
    """
    if signal not in SIGNAL_TYPES:
        raise ValueError(f"unknown proctor signal: {signal!r}")

    event = ProctorEvent(
        meeting_id=meeting.id,
        user_id=user.id,
        signal=signal,
        points=PROCTOR_SIGNALS[signal],
        minute=compute_minute(meeting),
        duration_s=clamp_duration(duration_s),
        detail=sanitize_detail(detail),
    )
    session.add(event)
    await session.flush()
    return event


def flag_out(
    event: ProctorEvent,
    name: str,
    *,
    clip_file_id: uuid.UUID | None = None,
    clip_status: str | None = None,
) -> ProctorFlagOut:
    """Shape one stored event as the host-facing flag DTO."""
    return ProctorFlagOut(
        id=event.id,
        user_id=event.user_id,
        name=name,
        signal=event.signal,
        label=PROCTOR_LABELS.get(event.signal, event.signal),
        points=event.points,
        minute=event.minute,
        duration_s=event.duration_s,
        created_at=event.created_at,
        clip_file_id=clip_file_id,
        clip_status=clip_status,
    )


async def list_recent_flags(
    session: AsyncSession, meeting_id: uuid.UUID, *, limit: int = 200
) -> list[tuple[ProctorEvent, str]]:
    """Most recent events with the student's display name, oldest first."""
    stmt = (
        select(ProctorEvent, User.display_name)
        .join(User, User.id == ProctorEvent.user_id)
        .where(ProctorEvent.meeting_id == meeting_id)
        .order_by(ProctorEvent.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1]) for row in reversed(rows)]


async def student_scores(session: AsyncSession, meeting_id: uuid.UUID) -> list[ProctorStudentOut]:
    """Per-student rollup (score, event count) for the host's live panel."""
    events = await session.execute(
        select(ProctorEvent.user_id, ProctorEvent.points).where(
            ProctorEvent.meeting_id == meeting_id
        )
    )
    totals: dict[uuid.UUID, tuple[int, int]] = {}
    for user_id, points in events.all():
        score, count = totals.get(user_id, (0, 0))
        totals[user_id] = (score + points, count + 1)

    participants = await session.execute(
        select(User, MeetingParticipant.joined_at)
        .join(MeetingParticipant, MeetingParticipant.user_id == User.id)
        .where(MeetingParticipant.meeting_id == meeting_id)
    )
    out: list[ProctorStudentOut] = []
    for user, joined_at in participants.unique().all():
        score, count = totals.get(user.id, (0, 0))
        out.append(
            ProctorStudentOut(
                user_id=user.id,
                name=user.display_name,
                email=str(user.email),
                score=score,
                event_count=count,
                joined_at=joined_at,
            )
        )
    out.sort(key=lambda s: (-s.score, s.name.lower()))
    return out


async def build_report(session: AsyncSession, meeting: Meeting) -> ReportOut:
    """Assemble the proctor's report: roster (present/absent) + event timeline.

    Roster = invitees plus actual joiners. An invitee who never joined is
    ABSENT; every joiner is PRESENT with their summed cheating score and
    timestamped events. The host is never listed (they are the proctor, not
    a student).
    """
    # --- actual joiners -----------------------------------------------------
    joiners = await session.execute(
        select(User, MeetingParticipant.joined_at, MeetingParticipant.left_at)
        .join(MeetingParticipant, MeetingParticipant.user_id == User.id)
        .where(
            MeetingParticipant.meeting_id == meeting.id,
            MeetingParticipant.user_id != meeting.host_id,
        )
        .order_by(MeetingParticipant.joined_at)
    )

    # Merge multiple join sessions per user (a rejoin is still one student).
    @dataclass
    class _Student:
        name: str
        email: str
        first_join: datetime | None = None
        last_leave: datetime | None = None

    merged: dict[uuid.UUID, _Student] = {}
    for user, joined_at, left_at in joiners.unique().all():
        entry = merged.setdefault(user.id, _Student(name=user.display_name, email=str(user.email)))
        if joined_at and (entry.first_join is None or joined_at < entry.first_join):
            entry.first_join = joined_at
        if left_at and (entry.last_leave is None or left_at > entry.last_leave):
            entry.last_leave = left_at

    # --- events per student ------------------------------------------------
    flags = await list_recent_flags(session, meeting.id, limit=5000)

    # Evidence clips keyed by event (newest record wins when a clip was
    # re-uploaded). Statuses — including failed/missing — flow into the report
    # so gaps are visible instead of silently absent.
    clip_rows = (
        await session.execute(
            select(StoredFile.id, StoredFile.upload_status, StoredFile.proctor_event_id)
            .where(
                StoredFile.meeting_id == meeting.id,
                StoredFile.proctor_event_id.is_not(None),
            )
            .order_by(StoredFile.created_at)
        )
    ).all()
    clips: dict[uuid.UUID, tuple[uuid.UUID, str]] = {
        row.proctor_event_id: (row.id, row.upload_status) for row in clip_rows
    }

    events_by_user: dict[uuid.UUID, list[ProctorFlagOut]] = {}
    for event, name in flags:
        clip = clips.get(event.id)
        events_by_user.setdefault(event.user_id, []).append(
            flag_out(
                event,
                name,
                clip_file_id=clip[0] if clip else None,
                clip_status=clip[1] if clip else None,
            )
        )

    students: list[ReportStudentOut] = []
    seen_emails: set[str] = set()

    for user_id, info in merged.items():
        events = events_by_user.get(user_id, [])
        score = sum(e.points for e in events)
        students.append(
            ReportStudentOut(
                name=info.name,
                email=info.email,
                status="PRESENT",
                cheating_score=score,
                events=events,
                joined_at=info.first_join,
                left_at=info.last_leave,
            )
        )
        seen_emails.add(info.email.lower())

    # --- invited-but-absent ------------------------------------------------
    invites = await session.scalars(
        select(MeetingInvite).where(MeetingInvite.meeting_id == meeting.id)
    )
    for invite in invites.all():
        if str(invite.email).lower() in seen_emails:
            continue
        students.append(
            ReportStudentOut(
                name="",
                email=str(invite.email),
                status="ABSENT",
                cheating_score=0,
            )
        )

    students.sort(key=lambda s: (s.status != "PRESENT", -s.cheating_score, s.email.lower()))

    return ReportOut(
        meeting_code=meeting.code,
        title=meeting.title,
        kind=meeting.kind,
        generated_at=datetime.now(UTC),
        started_at=meeting_clock_start(meeting),
        ended_at=meeting.ended_at,
        students=students,
    )


def report_to_csv(report: ReportOut) -> str:
    """Render the report as a CSV file the proctor can download.

    One row per event (so the timeline with points is explicit), plus a
    summary row per student. Uses ``csv`` for correct quoting. The clip
    columns carry the evidence reference and its *stored* status (``uploaded``
    / ``failed`` / ``missing``) — empty when no clip record exists.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "student",
            "email",
            "status",
            "cheating_score",
            "signal",
            "points",
            "minute",
            "clip_file_id",
            "clip_status",
        ]
    )
    for student in report.students:
        if not student.events:
            writer.writerow(
                [
                    student.name or "-",
                    student.email,
                    student.status,
                    student.cheating_score,
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue
        for event in student.events:
            writer.writerow(
                [
                    student.name or "-",
                    student.email,
                    student.status,
                    student.cheating_score,
                    event.label,
                    event.points,
                    event.minute,
                    str(event.clip_file_id) if event.clip_file_id else "",
                    event.clip_status or "",
                ]
            )
    return buf.getvalue()


def encode_detail(detail: dict[str, object] | None) -> str:
    """Compact JSON for a WS frame's detail field."""
    return json.dumps(detail or {}, separators=(",", ":"))
