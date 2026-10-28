"""File/evidence API tests (Phase 17 — D24 §7).

Full-stack integration against real infrastructure: Postgres for metadata,
Redis for rate limits, MinIO for bytes. Covers the authorization matrix
(owner/host only), content sniffing over declared types, size caps, clip to
proctoring-event binding, Range reads, signed URLs, deletion and legal hold,
retention sweeps, honest failure rows, drift detection, report integration,
and the audit trail.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app as fastapi_app
from app.models.audit import AuditLog
from app.models.file import StoredFile
from app.models.participant import MeetingParticipant
from app.models.proctor import ProctorEvent
from app.models.user import User
from app.services.storage_service import run_retention_sweep
from app.storage import (
    ObjectNotFoundError,
    ObjectStat,
    ObjectStorage,
    ObjectStream,
    StorageError,
    get_storage,
    storage_dep,
)
from tests.test_exam_proctoring import _create_exam
from tests.test_ws import _register

# Minimal files with real magic bytes (the sniffer ignores declared types).
PNG = b"\x89PNG\r\n\x1a\n" + b"procto-png" * 16
WEBM = b"\x1a\x45\xdf\xa3" + b"procto-webm" * 16
TXT = b"just some text without any magic bytes"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _user_id_by_email(email: str) -> uuid.UUID:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        return user.id


async def _meeting_id_by_code(client: AsyncClient, token: str, code: str) -> uuid.UUID:
    response = await client.get(f"/api/v1/meetings/{code}", headers=_auth(token))
    assert response.status_code == 200
    return uuid.UUID(str(response.json()["id"]))


async def _add_participant(meeting_id: Any, user_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        session.add(
            MeetingParticipant(
                meeting_id=uuid.UUID(str(meeting_id)),
                user_id=user_id,
                role="participant",
                joined_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _add_event(meeting_id: Any, user_id: uuid.UUID, signal: str = "looking_away") -> Any:
    async with SessionLocal() as session:
        event = ProctorEvent(
            meeting_id=uuid.UUID(str(meeting_id)),
            user_id=user_id,
            signal=signal,
            points=2,
            minute=1,
            duration_s=0.0,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event.id


async def _get_record(file_id: Any) -> StoredFile | None:
    async with SessionLocal() as session:
        return await session.get(StoredFile, uuid.UUID(str(file_id)))


async def _audit_actions(meeting_id: Any) -> list[str]:
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(AuditLog).where(AuditLog.meeting_id == uuid.UUID(str(meeting_id)))
            )
        ).all()
        return [str(row.action) for row in rows]


async def _upload(
    client: AsyncClient,
    token: str,
    code: str,
    *,
    content: bytes,
    purpose: str,
    filename: str = "upload.bin",
    declared_type: str = "application/octet-stream",
    event_id: Any = None,
) -> httpx.Response:
    data: dict[str, str] = {"purpose": purpose}
    if event_id is not None:
        data["event_id"] = str(event_id)
    return await client.post(
        f"/api/v1/meetings/{code}/files",
        files={"file": (filename, content, declared_type)},
        data=data,
        headers=_auth(token),
    )


async def _exam_with_student(
    client: AsyncClient, suffix: str = "a"
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Host auth, student auth, meeting code — student joined the meeting."""
    host = await _register(client, f"files-host-{suffix}@procto.dev", "Host")
    meeting = await _create_exam(client, host["access_token"])
    student = await _register(client, f"files-student-{suffix}@procto.dev", "Student")
    await _add_participant(
        meeting["id"], await _user_id_by_email(f"files-student-{suffix}@procto.dev")
    )
    return host, student, cast(str, meeting["code"])


class FailingStorage(ObjectStorage):
    """Provider stub whose every object operation fails (failure-row tests)."""

    name = "failing"

    async def ensure_bucket(self) -> None:
        return None

    async def put(
        self,
        key: str,
        fileobj: Any,
        *,
        content_type: str,
        length: int | None = None,
    ) -> None:
        raise StorageError("storage exploded")

    async def stat(self, key: str) -> ObjectStat | None:
        return None

    async def exists(self, key: str) -> bool:
        return False

    async def open(
        self, key: str, *, byte_range: tuple[int, int | None] | None = None
    ) -> ObjectStream:
        raise ObjectNotFoundError("gone")

    async def delete(self, key: str) -> None:
        return None

    def presign_get(self, key: str, *, expires_in: int) -> str:
        return "https://invalid.example/none"


class TestUpload:
    async def test_screenshot_upload_download_roundtrip(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client)

        response = await _upload(
            client,
            student["access_token"],
            code,
            content=PNG,
            purpose="screenshot",
            filename="board.png",
        )
        assert response.status_code == 201, response.text
        body = cast(dict[str, Any], response.json())
        assert body["upload_status"] == "uploaded"
        assert body["mime_type"] == "image/png"  # sniffed, not declared
        assert body["file_size"] == len(PNG)
        assert body["legal_hold"] is False

        listing = await client.get(
            f"/api/v1/meetings/{code}/files", headers=_auth(student["access_token"])
        )
        assert listing.status_code == 200
        assert [f["id"] for f in listing.json()["files"]] == [body["id"]]

        content = await client.get(
            f"/api/v1/meetings/{code}/files/{body['id']}/content",
            headers=_auth(student["access_token"]),
        )
        assert content.status_code == 200
        assert content.content == PNG
        assert content.headers["content-type"] == "image/png"

        actions = await _audit_actions(body["meeting_id"])
        assert "file_upload" in actions
        assert "file_download" in actions

    async def test_declared_content_type_is_ignored(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client, "b")

        response = await _upload(
            client,
            student["access_token"],
            code,
            content=PNG,
            purpose="screenshot",
            filename="notes.txt",
            declared_type="text/plain",
        )

        assert response.status_code == 201, response.text
        assert cast(dict[str, Any], response.json())["mime_type"] == "image/png"

    async def test_plain_text_is_rejected(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client, "c")

        response = await _upload(
            client, student["access_token"], code, content=TXT, purpose="attachment"
        )

        assert response.status_code == 400
        assert "supported format" in response.text

    async def test_unknown_purpose_is_rejected(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client, "d")

        response = await _upload(
            client, student["access_token"], code, content=PNG, purpose="diploma"
        )

        assert response.status_code == 400

    async def test_oversized_upload_is_rejected(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client, "e")

        big_png = PNG + b"\x00" * (10 * 1024 * 1024)  # screenshot cap is 10 MB
        response = await _upload(
            client, student["access_token"], code, content=big_png, purpose="screenshot"
        )

        assert response.status_code == 413

    async def test_non_participant_cannot_upload(self, client: AsyncClient) -> None:
        _host, _, code = await _exam_with_student(client, "f")
        stranger = await _register(client, "files-stranger@procto.dev", "Stranger")

        response = await _upload(
            client, stranger["access_token"], code, content=PNG, purpose="screenshot"
        )

        assert response.status_code == 403

    async def test_host_can_upload_screenshot(self, client: AsyncClient) -> None:
        host, _, code = await _exam_with_student(client, "g")

        response = await _upload(
            client, host["access_token"], code, content=PNG, purpose="screenshot"
        )

        assert response.status_code == 201, response.text

    async def test_upload_requires_auth(self, client: AsyncClient) -> None:
        _, _, code = await _exam_with_student(client, "h")

        response = await _upload(client, "not-a-token", code, content=PNG, purpose="screenshot")

        assert response.status_code == 401


class TestEvidenceClips:
    async def test_clip_requires_event_id(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client)

        response = await _upload(
            client, student["access_token"], code, content=WEBM, purpose="evidence_clip"
        )

        assert response.status_code == 400
        assert "event_id" in response.text

    async def test_clip_must_reference_own_event(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "b")
        meeting_id = await _meeting_id_by_code(client, host["access_token"], code)
        # An event that belongs to the *host*, not the uploading student.
        host_event = await _add_event(
            meeting_id, await _user_id_by_email("files-host-b@procto.dev")
        )

        response = await _upload(
            client,
            student["access_token"],
            code,
            content=WEBM,
            purpose="evidence_clip",
            event_id=host_event,
        )

        assert response.status_code == 400

    async def test_clip_needs_proctored_exam(self, client: AsyncClient) -> None:
        host = await _register(client, "files-std-host@procto.dev", "Host")
        created = await client.post(
            "/api/v1/meetings",
            json={"title": "standup"},
            headers=_auth(host["access_token"]),
        )
        code = cast(str, created.json()["code"])

        response = await _upload(
            client, host["access_token"], code, content=WEBM, purpose="evidence_clip"
        )

        assert response.status_code == 400
        assert "exam" in response.text

    async def test_clip_roundtrip_and_report_integration(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "c")
        meeting_id = await _meeting_id_by_code(client, host["access_token"], code)
        student_id = await _user_id_by_email("files-student-c@procto.dev")
        event_id = await _add_event(meeting_id, student_id)

        upload = await _upload(
            client,
            student["access_token"],
            code,
            content=WEBM,
            purpose="evidence_clip",
            filename="clip.webm",
            event_id=event_id,
        )
        assert upload.status_code == 201, upload.text
        file_id = cast(dict[str, Any], upload.json())["id"]

        report = await client.get(
            f"/api/v1/meetings/{code}/report.csv", headers=_auth(host["access_token"])
        )
        assert report.status_code == 200
        assert file_id in report.text
        assert "uploaded" in report.text
        assert "clip_file_id" in report.text
        assert "report_download" in await _audit_actions(meeting_id)

    async def test_second_clip_for_same_event_conflicts(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "d")
        meeting_id = await _meeting_id_by_code(client, host["access_token"], code)
        student_id = await _user_id_by_email("files-student-d@procto.dev")
        event_id = await _add_event(meeting_id, student_id)

        first = await _upload(
            client,
            student["access_token"],
            code,
            content=WEBM,
            purpose="evidence_clip",
            event_id=event_id,
        )
        assert first.status_code == 201

        second = await _upload(
            client,
            student["access_token"],
            code,
            content=WEBM + b"-v2",
            purpose="evidence_clip",
            event_id=event_id,
        )
        assert second.status_code == 409

    async def test_malformed_event_id_rejected(self, client: AsyncClient) -> None:
        _host, student, code = await _exam_with_student(client, "e")

        response = await _upload(
            client,
            student["access_token"],
            code,
            content=WEBM,
            purpose="evidence_clip",
            event_id="not-a-uuid",
        )

        assert response.status_code == 400


class TestAuthorization:
    async def test_other_student_cannot_read_file(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client)
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        # A second student who joined the same meeting still cannot read it.
        peer = await _register(client, "files-peer@procto.dev", "Peer")
        await _add_participant(
            await _meeting_id_by_code(client, host["access_token"], code),
            await _user_id_by_email("files-peer@procto.dev"),
        )
        response = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/content", headers=_auth(peer["access_token"])
        )

        assert response.status_code == 404  # no existence oracle

    async def test_host_can_read_any_file(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "b")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        response = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/content", headers=_auth(host["access_token"])
        )

        assert response.status_code == 200
        assert response.content == PNG

    async def test_unauthenticated_read_rejected(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client, "c")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        response = await client.get(f"/api/v1/meetings/{code}/files/{file_id}/content")

        assert response.status_code == 401

    async def test_cross_meeting_file_is_not_found(self, client: AsyncClient) -> None:
        _host_a, student_a, code_a = await _exam_with_student(client, "d")
        upload = await _upload(
            client, student_a["access_token"], code_a, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        _, student_b, code_b = await _exam_with_student(client, "e")
        response = await client.get(
            f"/api/v1/meetings/{code_b}/files/{file_id}/content",
            headers=_auth(student_b["access_token"]),
        )

        assert response.status_code == 404

    async def test_list_is_scoped_to_owner(self, client: AsyncClient) -> None:
        host, student_a, code = await _exam_with_student(client, "f")
        student_b = await _register(client, "files-student-g@procto.dev", "StudentB")
        await _add_participant(
            await _meeting_id_by_code(client, host["access_token"], code),
            await _user_id_by_email("files-student-g@procto.dev"),
        )
        await _upload(client, student_a["access_token"], code, content=PNG, purpose="screenshot")
        await _upload(client, student_b["access_token"], code, content=WEBM, purpose="attachment")

        as_b = await client.get(
            f"/api/v1/meetings/{code}/files", headers=_auth(student_b["access_token"])
        )
        as_host = await client.get(
            f"/api/v1/meetings/{code}/files", headers=_auth(host["access_token"])
        )

        files_b = cast(list[dict[str, Any]], as_b.json()["files"])
        assert len(files_b) == 1
        assert files_b[0]["user_id"] == str(await _user_id_by_email("files-student-g@procto.dev"))
        assert len(cast(list[dict[str, Any]], as_host.json()["files"])) == 2


class TestContentDelivery:
    async def test_range_request_serves_partial_content(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client)
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        response = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/content",
            headers={**_auth(student["access_token"]), "Range": "bytes=0-3"},
        )

        assert response.status_code == 206
        assert response.content == PNG[:4]
        assert response.headers["content-range"] == f"bytes 0-3/{len(PNG)}"

    async def test_presigned_url_flow(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client, "b")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        signed = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/url",
            headers=_auth(student["access_token"]),
        )
        assert signed.status_code == 200, signed.text
        payload = cast(dict[str, Any], signed.json())
        assert 10 <= payload["expires_in"] <= 3600

        async with httpx.AsyncClient() as direct:
            fetched = await direct.get(cast(str, payload["url"]))
        assert fetched.status_code == 200
        assert fetched.content == PNG


class TestLifecycle:
    async def test_delete_removes_object_and_hides_file(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client)
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]
        record = await _get_record(file_id)
        assert record is not None

        deleted = await client.delete(
            f"/api/v1/meetings/{code}/files/{file_id}", headers=_auth(student["access_token"])
        )
        assert deleted.status_code == 200
        assert cast(dict[str, Any], deleted.json())["upload_status"] in ("deleted", "purged")

        content = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/content",
            headers=_auth(student["access_token"]),
        )
        assert content.status_code == 404
        assert await get_storage().stat(record.storage_key) is None

        row = await _get_record(file_id)
        assert row is not None
        assert row.deleted_at is not None
        assert "file_delete" in await _audit_actions(row.meeting_id)

    async def test_legal_hold_blocks_deletion(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "b")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        held = await client.post(
            f"/api/v1/meetings/{code}/files/{file_id}/hold",
            json={"hold": True},
            headers=_auth(host["access_token"]),
        )
        assert held.status_code == 200
        assert cast(dict[str, Any], held.json())["legal_hold"] is True

        blocked = await client.delete(
            f"/api/v1/meetings/{code}/files/{file_id}", headers=_auth(student["access_token"])
        )
        assert blocked.status_code == 409

    async def test_hold_is_host_only(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client, "c")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]

        response = await client.post(
            f"/api/v1/meetings/{code}/files/{file_id}/hold",
            json={"hold": True},
            headers=_auth(student["access_token"]),
        )

        assert response.status_code == 403

    async def test_failed_upload_is_recorded_honestly(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "d")
        fastapi_app.dependency_overrides[storage_dep] = lambda: FailingStorage()
        try:
            response = await _upload(
                client, student["access_token"], code, content=PNG, purpose="screenshot"
            )
        finally:
            fastapi_app.dependency_overrides.pop(storage_dep, None)

        assert response.status_code == 502

        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(StoredFile).where(
                        StoredFile.meeting_id
                        == await _meeting_id_by_code(client, host["access_token"], code)
                    )
                )
            ).all()
        assert [row.upload_status for row in rows] == ["failed"]

    async def test_missing_object_drift_is_detected(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client, "e")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]
        record = await _get_record(file_id)
        assert record is not None
        await get_storage().delete(record.storage_key)

        content = await client.get(
            f"/api/v1/meetings/{code}/files/{file_id}/content",
            headers=_auth(student["access_token"]),
        )
        assert content.status_code == 404

        row = await _get_record(file_id)
        assert row is not None
        assert row.upload_status == "missing"


class TestRetention:
    async def test_sweep_purges_expired_files(self, client: AsyncClient) -> None:
        _, student, code = await _exam_with_student(client)
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]
        record = await _get_record(file_id)
        assert record is not None
        storage_key = record.storage_key

        async with SessionLocal() as session:
            row = await session.get(StoredFile, uuid.UUID(str(file_id)))
            assert row is not None
            row.retention_expires_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()

        purged = await run_retention_sweep(get_storage())

        assert purged >= 1
        row = await _get_record(file_id)
        assert row is not None
        assert row.deleted_at is not None
        assert row.upload_status == "purged"
        assert await get_storage().stat(storage_key) is None

    async def test_sweep_respects_legal_hold(self, client: AsyncClient) -> None:
        host, student, code = await _exam_with_student(client, "b")
        upload = await _upload(
            client, student["access_token"], code, content=PNG, purpose="screenshot"
        )
        file_id = cast(dict[str, Any], upload.json())["id"]
        await client.post(
            f"/api/v1/meetings/{code}/files/{file_id}/hold",
            json={"hold": True},
            headers=_auth(host["access_token"]),
        )

        async with SessionLocal() as session:
            row = await session.get(StoredFile, uuid.UUID(str(file_id)))
            assert row is not None
            row.retention_expires_at = datetime.now(UTC) - timedelta(days=1)
            await session.commit()

        await run_retention_sweep(get_storage())

        row = await _get_record(file_id)
        assert row is not None
        assert row.deleted_at is None
        assert row.upload_status == "uploaded"
