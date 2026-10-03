"""Meeting request/response contracts (Phase 3)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateMeetingRequest(BaseModel):
    """Optional title when starting a meet."""

    title: str | None = Field(default=None, max_length=120)


class MeetingOut(BaseModel):
    """Public meeting representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    title: str | None
    host_id: UUID
    status: str
    is_locked: bool
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class LiveKitTokenOut(BaseModel):
    """Ephemeral SFU credentials for joining the meeting's LiveKit room."""

    url: str
    token: str
