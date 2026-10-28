"""Object-storage request/response contracts (Phase 17 — D24)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FilePurpose = Literal["evidence_clip", "screenshot", "attachment"]

# Public statuses a client may observe (matches the DB check constraint).
FileStatus = Literal["pending", "uploaded", "failed", "missing", "deleted", "purged"]


class FileOut(BaseModel):
    """One stored object's metadata (key/URLs are never exposed)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    meeting_id: UUID
    user_id: UUID
    proctor_event_id: UUID | None = None
    purpose: FilePurpose
    mime_type: str
    file_size: int
    original_name: str | None = None
    upload_status: FileStatus
    legal_hold: bool = False
    created_at: datetime
    retention_expires_at: datetime | None = None


class FileListOut(BaseModel):
    """Files visible to the caller (host: whole meeting; others: own only)."""

    files: list[FileOut] = Field(default_factory=list)


class PresignedUrlOut(BaseModel):
    """Short-lived signed URL for direct object access (server-authorized first)."""

    url: str
    expires_in: int
    expires_at: datetime


class FileHoldRequest(BaseModel):
    """Freeze/unfreeze a file out of retention cleanup (host, appeal cases)."""

    hold: bool
