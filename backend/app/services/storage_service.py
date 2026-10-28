"""Object-storage orchestration: validation, lifecycle, authz, retention (D24).

This is the only module (together with ``app.storage``) that knows how bytes
move. Routes stay thin: they authenticate, delegate here, and translate the
closed exception set below into HTTP statuses.

Design rules from the decision doc:

* **Validate content, not labels** — the sniffed magic bytes are authoritative;
  a declared ``Content-Type`` never decides what a file is.
* **Failures are first-class rows** — an upload that never landed is persisted
  as ``failed`` so reports show the gap instead of pretending it never happened.
* **Retention respects holds** — ``legal_hold`` files are invisible to the
  sweeper and refuse manual deletion.
* **Keys, never URLs** — records store provider-private object keys only.
"""

import asyncio
import logging
import os
import tempfile
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.models.file import StoredFile
from app.models.meeting import Meeting
from app.models.participant import MeetingParticipant
from app.models.proctor import ProctorEvent
from app.models.user import User
from app.storage import ObjectStorage

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Exceptions (closed set — routes map each to an HTTP status)
# --------------------------------------------------------------------------------------


class FileValidationError(ValueError):
    """Request is semantically invalid → HTTP 400."""


class FileTooLargeError(FileValidationError):
    """Upload exceeds the per-purpose byte cap → HTTP 413."""


class DuplicateFileError(FileValidationError):
    """An active file already occupies a unique slot → HTTP 409."""


class FileOnHoldError(FileValidationError):
    """The file is under legal hold (appeal/preservation) → HTTP 409."""


# --------------------------------------------------------------------------------------
# Purpose configuration (size caps + allowed content types per purpose)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PurposeSpec:
    mimes: frozenset[str]
    max_bytes: int


_MB = 1024 * 1024

PURPOSE_CONFIG: dict[str, PurposeSpec] = {
    "evidence_clip": PurposeSpec(
        mimes=frozenset({"video/webm", "video/mp4"}),
        max_bytes=50 * _MB,
    ),
    "screenshot": PurposeSpec(
        mimes=frozenset({"image/png", "image/jpeg", "image/webp"}),
        max_bytes=10 * _MB,
    ),
    "attachment": PurposeSpec(
        mimes=frozenset(
            {
                "image/png",
                "image/jpeg",
                "image/webp",
                "application/pdf",
                "video/webm",
                "video/mp4",
            }
        ),
        max_bytes=25 * _MB,
    ),
}

_EXT_BY_MIME = {
    "video/webm": ".webm",
    "video/mp4": ".mp4",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

# Multipart body slack (boundaries + other parts) allowed over the file cap
# in the Content-Length pre-check, before the body is parsed.
BODY_SLACK_BYTES = 2 * _MB

_UPLOAD_SPOOL_CHUNK = 64 * 1024
_SNIFF_BYTES = 16


# --------------------------------------------------------------------------------------
# Pure helpers (unit-tested without any infrastructure)
# --------------------------------------------------------------------------------------


def sniff_mime(head: bytes) -> str | None:
    """Identify the true content type from magic bytes (None = unknown)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML — WebM/Matroska container
        return "video/webm"
    if len(head) >= 8 and head[4:8] == b"ftyp":  # ISO-BMFF — MP4
        return "video/mp4"
    return None


def build_storage_key(meeting_id: uuid.UUID, purpose: str, file_id: uuid.UUID, mime: str) -> str:
    """Provider-private object key: no PII, no extension guessing, no URLs."""
    ext = _EXT_BY_MIME.get(mime, ".bin")
    return f"meetings/{meeting_id}/{purpose}/{file_id}{ext}"


def sanitize_filename(name: str | None) -> str | None:
    """Strip path components and non-printables from a client filename."""
    if not name:
        return None
    cleaned = name.replace("\\", "/").split("/")[-1]
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())
    return cleaned[:255] or None


def retention_deadline(at: datetime | None = None) -> datetime | None:
    """When automatic retention may purge this file (None = keep forever)."""
    days = settings.storage_retention_days
    if days <= 0:
        return None
    base = at or datetime.now(UTC)
    return base + timedelta(days=days)


async def spool_upload(upload: UploadFile, *, max_bytes: int) -> tuple[str, int, bytes]:
    """Stream an upload to a temp file while enforcing ``max_bytes``.

    Returns ``(temp_path, size, head)`` where ``head`` is the first 16 bytes
    (enough for every magic-byte signature). The temp file is caller-owned and
    must be unlinked. Raises :class:`FileTooLargeError` past the cap.
    """
    fd, path = tempfile.mkstemp(prefix="procto-upload-")
    size = 0
    head = b""
    try:
        with os.fdopen(fd, "wb") as tmp:
            while True:
                chunk = await upload.read(_UPLOAD_SPOOL_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(
                        f"file exceeds the {max_bytes // _MB} MB limit for this upload"
                    )
                if len(head) < _SNIFF_BYTES:
                    head += chunk[: _SNIFF_BYTES - len(head)]
                tmp.write(chunk)
    except BaseException:
        _unlink_quietly(path)
        raise
    return path, size, head


# --------------------------------------------------------------------------------------
# Authorization helpers (server-side, never client-trusted — D24 §6)
# --------------------------------------------------------------------------------------


async def has_joined_meeting(
    session: AsyncSession, meeting_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """True when the user has a join record for this meeting (any session)."""
    row = await session.scalar(
        select(MeetingParticipant.id)
        .where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.user_id == user_id,
        )
        .limit(1)
    )
    return row is not None


def can_access_file(meeting: Meeting, record: StoredFile, user: User) -> bool:
    """Owner or the meeting's host — nobody else ever reads private evidence."""
    return str(record.user_id) == str(user.id) or str(meeting.host_id) == str(user.id)


def is_host(meeting: Meeting, user: User) -> bool:
    return str(meeting.host_id) == str(user.id)


# --------------------------------------------------------------------------------------
# Lifecycle operations
# --------------------------------------------------------------------------------------


async def get_active_record(
    session: AsyncSession, meeting_id: uuid.UUID, file_id: uuid.UUID
) -> StoredFile | None:
    """Load a non-deleted file scoped to its meeting (IDOR-safe lookup)."""
    return await session.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id,
            StoredFile.meeting_id == meeting_id,
            StoredFile.deleted_at.is_(None),
        )
    )


async def upload_meeting_file(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    meeting: Meeting,
    user: User,
    upload: UploadFile,
    purpose: str,
    event_id: uuid.UUID | None = None,
    original_name: str | None = None,
) -> StoredFile:
    """Validate + persist + upload one file; commits its own outcome.

    Row lifecycle: ``pending`` (flushed) → ``uploaded`` or ``failed`` (committed)
    so a report can distinguish "never attempted" from "attempted and failed".
    """
    spec = PURPOSE_CONFIG.get(purpose)
    if spec is None:
        raise FileValidationError(
            f"unknown purpose {purpose!r}; expected one of {sorted(PURPOSE_CONFIG)}"
        )

    path, size, head = await spool_upload(upload, max_bytes=spec.max_bytes)
    try:
        if size == 0:
            raise FileValidationError("file is empty")
        mime = sniff_mime(head)
        if mime is None:
            raise FileValidationError("file content does not match any supported format")
        if mime not in spec.mimes:
            raise FileValidationError(f"{mime} files are not allowed for {purpose}")

        # Evidence clips must attach to *this user's* event in *this* exam.
        proctor_event: ProctorEvent | None = None
        if purpose == "evidence_clip":
            if meeting.kind != "exam" or not meeting.proctoring_enabled:
                raise FileValidationError(
                    "evidence clips can only be uploaded to a proctored exam meeting"
                )
            if event_id is None:
                raise FileValidationError("event_id is required for evidence clips")
            proctor_event = await session.scalar(
                select(ProctorEvent).where(
                    ProctorEvent.id == event_id,
                    ProctorEvent.meeting_id == meeting.id,
                    ProctorEvent.user_id == user.id,
                )
            )
            if proctor_event is None:
                raise FileValidationError("unknown proctoring event for this meeting")

        # One active clip per event: retries reuse a failed/pending row; an
        # uploaded one conflicts (the partial unique index backs this up).
        record: StoredFile | None = None
        if proctor_event is not None:
            record = await session.scalar(
                select(StoredFile).where(
                    StoredFile.proctor_event_id == proctor_event.id,
                    StoredFile.deleted_at.is_(None),
                )
            )
            if record is not None and record.upload_status == "uploaded":
                raise DuplicateFileError("a clip is already attached to this event")

        if record is None:
            record = StoredFile(
                id=uuid.uuid4(),
                meeting_id=meeting.id,
                user_id=user.id,
                proctor_event_id=proctor_event.id if proctor_event else None,
                purpose=purpose,
                provider=storage.name,
                mime_type=mime,
                file_size=size,
                original_name=sanitize_filename(original_name),
                upload_status="pending",
                retention_expires_at=retention_deadline(),
            )
            record.storage_key = build_storage_key(meeting.id, purpose, record.id, mime)
            session.add(record)
        else:  # retry of a failed/pending upload — refresh the attempt in place
            record.provider = storage.name
            record.mime_type = mime
            record.file_size = size
            record.original_name = sanitize_filename(original_name)
            record.upload_status = "pending"
            record.retention_expires_at = record.retention_expires_at or retention_deadline()
            record.storage_key = build_storage_key(meeting.id, purpose, record.id, mime)

        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateFileError("a clip is already attached to this event") from exc

        # --- move the bytes ------------------------------------------------------
        try:
            await storage.ensure_bucket()
            with open(path, "rb") as fh:
                await storage.put(record.storage_key, fh, content_type=mime, length=size)
        except Exception:
            # Persist the failure honestly (own commit): reports must show it.
            record.upload_status = "failed"
            await session.commit()
            logger.warning(
                "object upload failed (file=%s meeting=%s)", record.id, meeting.id, exc_info=True
            )
            raise
        record.upload_status = "uploaded"
        await session.commit()
        return record
    finally:
        _unlink_quietly(path)


async def mark_missing(session: AsyncSession, record: StoredFile) -> None:
    """Record drift: the row claims bytes that the store no longer has."""
    if record.upload_status == "uploaded":
        record.upload_status = "missing"
        await session.commit()
        logger.error("stored object missing while row says uploaded (file=%s)", record.id)


async def delete_record(
    session: AsyncSession, *, storage: ObjectStorage, record: StoredFile
) -> StoredFile:
    """Soft-delete a file: tombstone the row, then remove the object.

    Object deletion is attempted immediately; failures leave the row at
    ``deleted`` so the retention sweeper retries until the bytes are gone.
    """
    if record.legal_hold:
        raise FileOnHoldError("file is under legal hold and cannot be deleted")
    now = datetime.now(UTC)
    record.deleted_at = now
    record.upload_status = "deleted"
    await session.flush()
    if await _delete_object(storage, record):
        record.upload_status = "purged"
    await session.commit()
    return record


async def _delete_object(storage: ObjectStorage, record: StoredFile) -> bool:
    """Best-effort object removal; False leaves the row for a later retry."""
    try:
        await storage.delete(record.storage_key)
        return True
    except Exception:
        logger.error(
            "object delete failed; will retry via retention sweep (file=%s)",
            record.id,
            exc_info=True,
        )
        return False


async def purge_expired_files(
    session: AsyncSession, *, storage: ObjectStorage, now: datetime | None = None
) -> int:
    """Retention sweep (D24 §6/§8): expire overdue files, honour legal holds.

    Two passes: (1) active files past ``retention_expires_at`` are tombstoned
    and their objects removed; (2) tombstones whose object deletion failed
    earlier are retried. Returns the number of objects confirmed gone.
    """
    now = now or datetime.now(UTC)
    purged = 0

    expired = (
        (
            await session.execute(
                select(StoredFile).where(
                    StoredFile.retention_expires_at.is_not(None),
                    StoredFile.retention_expires_at <= now,
                    StoredFile.deleted_at.is_(None),
                    StoredFile.legal_hold.is_(False),
                    StoredFile.upload_status.in_(("uploaded", "pending", "failed", "missing")),
                )
            )
        )
        .scalars()
        .all()
    )
    for record in expired:
        record.deleted_at = now
        record.upload_status = "deleted"
        if await _delete_object(storage, record):
            record.upload_status = "purged"
            purged += 1

    stale = (
        (
            await session.execute(
                select(StoredFile).where(
                    StoredFile.deleted_at.is_not(None),
                    StoredFile.upload_status == "deleted",
                    StoredFile.legal_hold.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for record in stale:
        if await _delete_object(storage, record):
            record.upload_status = "purged"
            purged += 1

    await session.commit()
    if expired or stale:
        logger.info("retention sweep purged %d object(s)", purged)
    return purged


# --------------------------------------------------------------------------------------
# Background sweeper wiring (lifespan)
# --------------------------------------------------------------------------------------


async def run_retention_sweep(storage: ObjectStorage) -> int:
    """One sweep in its own session (used by the background loop and tests)."""
    from app.db import SessionLocal

    async with SessionLocal() as session:
        return await purge_expired_files(session, storage=storage)


async def retention_sweep_loop(interval_hours: float, *, storage: ObjectStorage) -> None:
    """Background sweeper: sleep first, then purge forever (cancelled at shutdown).

    Sleeps before the first run so application startup never races the sweeper;
    failures are logged and never kill the loop.
    """
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await run_retention_sweep(storage)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention sweep failed")


def _unlink_quietly(path: str) -> None:
    with suppress(OSError):
        os.unlink(path)


# Re-export for routes/tests that orchestrate reads.
__all__ = [
    "BODY_SLACK_BYTES",
    "PURPOSE_CONFIG",
    "DuplicateFileError",
    "FileOnHoldError",
    "FileTooLargeError",
    "FileValidationError",
    "PurposeSpec",
    "build_storage_key",
    "can_access_file",
    "delete_record",
    "get_active_record",
    "has_joined_meeting",
    "is_host",
    "mark_missing",
    "purge_expired_files",
    "retention_deadline",
    "retention_sweep_loop",
    "run_retention_sweep",
    "sanitize_filename",
    "sniff_mime",
    "spool_upload",
    "upload_meeting_file",
]
