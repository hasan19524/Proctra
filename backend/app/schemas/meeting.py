"""Meeting request/response contracts (Phases 3, 13, 16 — exam mode)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Cap on the invite roster a single create request can carry.
MAX_INVITE_EMAILS = 200


class CreateMeetingRequest(BaseModel):
    """Optional title, join guards, and exam settings when starting a meet.

    Phase 16 added the exam-mode fields: ``kind="exam"`` requires a password
    and turns on the proctoring pipeline; ``invite_emails`` seeds the roster
    the report's present/absent columns are graded against.
    """

    title: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=64)
    waiting_room: bool = False
    kind: Literal["standard", "exam"] = "standard"
    proctoring_enabled: bool = True
    invite_emails: list[str] = Field(default_factory=list, max_length=MAX_INVITE_EMAILS)

    @model_validator(mode="after")
    def exam_requires_password(self) -> "CreateMeetingRequest":
        """An exam without a password would be open to anyone with the code."""
        if self.kind == "exam" and not self.password:
            raise ValueError("Exam meetings require a join password")
        return self


class MeetingOut(BaseModel):
    """Public meeting representation.

    ``password_hash`` never appears here: clients only learn *whether* a
    password exists (``has_password``).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    title: str | None
    host_id: UUID
    status: str
    kind: str = "standard"
    is_locked: bool
    waiting_room: bool = False
    has_password: bool = False
    proctoring_enabled: bool = False
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class MeetingHistoryOut(BaseModel):
    """Meeting summary for the user's history (Phase 14)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    title: str | None
    host_id: UUID
    status: str
    kind: str = "standard"
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    joined_at: datetime | None = None


class LiveKitTokenRequest(BaseModel):
    """Join password echoed back for verification when the meeting has one."""

    password: str | None = Field(default=None, max_length=64)


class LiveKitTokenOut(BaseModel):
    """Ephemeral SFU credentials for joining the meeting's LiveKit room."""

    url: str
    token: str


class ProctorFlagOut(BaseModel):
    """One proctoring event, as fanned out to the host over the WS."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    signal: str
    label: str
    points: int
    minute: int
    duration_s: float
    created_at: datetime


class ProctorStudentOut(BaseModel):
    """Per-student rollup for the host's live integrity panel."""

    user_id: UUID
    name: str
    email: str
    score: int
    event_count: int
    joined_at: datetime | None = None


class ReportStudentOut(BaseModel):
    """One row of the proctor's downloadable report."""

    name: str
    email: str
    status: Literal["PRESENT", "ABSENT"]
    cheating_score: int
    events: list[ProctorFlagOut] = Field(default_factory=list)
    joined_at: datetime | None = None
    left_at: datetime | None = None


class ReportOut(BaseModel):
    """Full exam report: roster + per-student scores + event timeline."""

    meeting_code: str
    title: str | None
    kind: str
    generated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    students: list[ReportStudentOut] = Field(default_factory=list)
