"""Meeting request/response contracts (Phases 3, 13)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateMeetingRequest(BaseModel):
    """Optional title and join guards when starting a meet (Phase 13)."""

    title: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=64)
    waiting_room: bool = False


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
    is_locked: bool
    waiting_room: bool = False
    has_password: bool = False
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
