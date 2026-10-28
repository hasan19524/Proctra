"""Meeting file routes (Phase 17 — object storage, DECISIONS.md D24).

Private-by-default evidence storage: every route authenticates, loads the
meeting, and authorizes server-side before a single byte moves.

Authz matrix (D24 §6):

* upload — meeting host or any participant that ever joined the meeting;
* read (metadata/content/signed URL) — file owner or meeting host only;
* hold/delete — hold is host-only; delete is owner or host.

Bytes are proxied through the backend by default so the strict CSP stays intact
and every access is auditable; the signed-URL route (short TTL) exists for API
consumers and is authorized before the URL is minted.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.ratelimit import rate_limit
from app.db import get_session
from app.models.file import StoredFile
from app.models.meeting import Meeting
from app.models.user import User
from app.schemas.storage import FileHoldRequest, FileListOut, FileOut, PresignedUrlOut
from app.services import meeting_service
from app.services.audit_service import audit
from app.services.meeting_service import MeetingNotFoundError
from app.services.storage_service import (
    BODY_SLACK_BYTES,
    PURPOSE_CONFIG,
    DuplicateFileError,
    FileOnHoldError,
    FileTooLargeError,
    FileValidationError,
    can_access_file,
    delete_record,
    get_active_record,
    has_joined_meeting,
    is_host,
    mark_missing,
    upload_meeting_file,
)
from app.storage import (
    ObjectNotFoundError,
    ObjectStorage,
    RangeNotSatisfiableError,
    StorageError,
    StorageUnavailableError,
    storage_dep,
)

router = APIRouter(prefix="/meetings", tags=["files"])

# One closed single-range header ("bytes=10-99" / "bytes=10-"); anything else
# (suffix or multi-range) is ignored and the full object is served.
_SINGLE_RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")


def parse_range_header(header: str | None) -> tuple[int, int | None] | None:
    """Parse a single byte-range header; None = serve the full object."""
    if not header:
        return None
    match = _SINGLE_RANGE_RE.match(header.strip())
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else None
    if end is not None and end < start:
        return None
    return (start, end)


def _part_length(content_range: str | None) -> int | None:
    """Body length of a 206 response from ``Content-Range: bytes X-Y/total``."""
    if not content_range:
        return None
    try:
        span = content_range.split(" ", 1)[1].split("/", 1)[0]
        start_s, end_s = span.split("-", 1)
        return int(end_s) - int(start_s) + 1
    except (IndexError, ValueError):
        return None


def _map_file_error(exc: Exception) -> HTTPException:
    """Translate the storage-service exception set into HTTP statuses."""
    if isinstance(exc, FileTooLargeError):
        return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc))
    if isinstance(exc, DuplicateFileError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, FileOnHoldError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, FileValidationError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, StorageUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "object storage is unavailable")
    if isinstance(exc, StorageError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, "object storage upload failed")
    raise exc


async def _load_meeting(code: str, session: AsyncSession) -> Meeting:
    try:
        return await meeting_service.get_meeting_by_code(session, code)
    except MeetingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found") from exc


async def _require_member(meeting: Meeting, user: User, session: AsyncSession) -> Meeting:
    """Host or anyone who ever joined — file routes are never public."""
    if is_host(meeting, user):
        return meeting
    if await has_joined_meeting(session, meeting.id, user.id):
        return meeting
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Only meeting participants can access files")


async def _load_owned_file(
    code: str, file_id: uuid.UUID, user: User, session: AsyncSession
) -> tuple[Meeting, StoredFile]:
    """Meeting + active file, authorized for reading (owner or host)."""
    meeting = await _load_meeting(code, session)
    record = await get_active_record(session, meeting.id, file_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    if not can_access_file(meeting, record, user):
        # No existence oracle: another student's file is simply not found.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return meeting, record


@router.post("/{code}/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    code: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> FileOut:
    """Upload one evidence clip / screenshot / attachment (multipart).

    The body-size guard runs *before* multipart parsing so an oversized request
    is rejected without spooling gigabytes to disk.
    """
    meeting = await _load_meeting(code, session)
    await _require_member(meeting, user, session)
    await rate_limit("file_upload", str(user.id), 30, 60)

    body_cap = max(spec.max_bytes for spec in PURPOSE_CONFIG.values()) + BODY_SLACK_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > body_cap:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "upload body is too large")

    form = await request.form()
    raw_file = form.get("file")
    if not isinstance(raw_file, StarletteUploadFile):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "multipart field 'file' is required")
    purpose = str(form.get("purpose") or "")
    raw_event = form.get("event_id")
    try:
        event_id = uuid.UUID(str(raw_event)) if raw_event else None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "event_id must be a UUID") from exc

    try:
        record = await upload_meeting_file(
            session,
            storage=storage,
            meeting=meeting,
            user=user,
            upload=raw_file,
            purpose=purpose,
            event_id=event_id,
            original_name=raw_file.filename,
        )
    except (FileValidationError, StorageError) as exc:
        raise _map_file_error(exc) from exc
    finally:
        await raw_file.close()

    await audit(
        session,
        meeting_id=meeting.id,
        actor_id=user.id,
        action="file_upload",
        target_id=record.id,
        detail={"purpose": record.purpose, "size": record.file_size, "mime": record.mime_type},
    )
    await session.commit()
    return FileOut.model_validate(record)


@router.get("/{code}/files", response_model=FileListOut)
async def list_files(
    code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileListOut:
    """Active files the caller may see (host: whole meeting; others: own only)."""
    meeting = await _load_meeting(code, session)
    await _require_member(meeting, user, session)
    stmt = (
        select(StoredFile)
        .where(StoredFile.meeting_id == meeting.id, StoredFile.deleted_at.is_(None))
        .order_by(StoredFile.created_at)
    )
    if not is_host(meeting, user):
        stmt = stmt.where(StoredFile.user_id == user.id)
    rows = (await session.execute(stmt)).scalars().all()
    return FileListOut(files=[FileOut.model_validate(row) for row in rows])


@router.get("/{code}/files/{file_id}", response_model=FileOut)
async def get_file_meta(
    code: str,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileOut:
    """One file's metadata (owner or host)."""
    _, record = await _load_owned_file(code, file_id, user, session)
    return FileOut.model_validate(record)


@router.get("/{code}/files/{file_id}/content")
async def stream_file_content(
    code: str,
    file_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> StreamingResponse:
    """Proxy the object's bytes (server-authorized, Range-capable for seeking)."""
    meeting, record = await _load_owned_file(code, file_id, user, session)
    await rate_limit("file_fetch", str(user.id), 120, 60)

    byte_range = parse_range_header(request.headers.get("range"))
    try:
        stream = await storage.open(record.storage_key, byte_range=byte_range)
    except ObjectNotFoundError as exc:
        await mark_missing(session, record)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File content is missing") from exc
    except RangeNotSatisfiableError as exc:
        raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Range not satisfiable") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "object storage is unavailable"
        ) from exc
    except StorageError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "object storage read failed") from exc

    await audit(
        session,
        meeting_id=meeting.id,
        actor_id=user.id,
        action="file_download",
        target_id=record.id,
        detail={"mode": "range" if byte_range else "full", "status": stream.status},
    )
    await session.commit()

    disposition = quote(record.original_name or record.storage_key.rsplit("/", 1)[-1])
    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{disposition}",
        "X-Content-Type-Options": "nosniff",
    }
    length = stream.size if stream.status == 200 else _part_length(stream.content_range)
    if length is not None:
        headers["Content-Length"] = str(length)
    if stream.content_range:
        headers["Content-Range"] = stream.content_range
    return StreamingResponse(
        stream.chunks, status_code=stream.status, media_type=stream.content_type, headers=headers
    )


@router.get("/{code}/files/{file_id}/url", response_model=PresignedUrlOut)
async def get_presigned_url(
    code: str,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> PresignedUrlOut:
    """Mint a short-lived signed URL (authorized first; TTL from settings)."""
    meeting, record = await _load_owned_file(code, file_id, user, session)
    await rate_limit("file_fetch", str(user.id), 120, 60)

    stat = await storage.stat(record.storage_key)
    if stat is None:
        await mark_missing(session, record)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File content is missing")

    ttl = max(10, min(settings.storage_signed_url_ttl_seconds, 3600))
    url = storage.presign_get(record.storage_key, expires_in=ttl)

    await audit(
        session,
        meeting_id=meeting.id,
        actor_id=user.id,
        action="file_download",
        target_id=record.id,
        detail={"mode": "presigned", "expires_in": ttl},
    )
    await session.commit()
    return PresignedUrlOut(
        url=url, expires_in=ttl, expires_at=datetime.now(UTC) + timedelta(seconds=ttl)
    )


@router.post("/{code}/files/{file_id}/hold", response_model=FileOut)
async def set_file_hold(
    code: str,
    file_id: uuid.UUID,
    body: FileHoldRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileOut:
    """Freeze/unfreeze a file out of retention cleanup (host only, appeals)."""
    meeting = await _load_meeting(code, session)
    if not is_host(meeting, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the host can change legal hold")
    record = await get_active_record(session, meeting.id, file_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    record.legal_hold = body.hold
    await audit(
        session,
        meeting_id=meeting.id,
        actor_id=user.id,
        action="file_hold",
        target_id=record.id,
        detail={"hold": body.hold},
    )
    await session.commit()
    return FileOut.model_validate(record)


@router.delete("/{code}/files/{file_id}", response_model=FileOut)
async def delete_file(
    code: str,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> FileOut:
    """Soft-delete a file: tombstone the row, remove the object (owner or host)."""
    meeting, record = await _load_owned_file(code, file_id, user, session)
    try:
        record = await delete_record(session, storage=storage, record=record)
    except FileOnHoldError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await audit(
        session,
        meeting_id=meeting.id,
        actor_id=user.id,
        action="file_delete",
        target_id=record.id,
        detail={"status": record.upload_status},
    )
    await session.commit()
    return FileOut.model_validate(record)
