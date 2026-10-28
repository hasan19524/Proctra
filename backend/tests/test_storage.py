"""Object storage tests (Phase 17 — D24 §7).

Unit: provider selection and config validation (fail clearly at startup), plus
the pure content-validation helpers — no infrastructure needed.

Integration: the real local MinIO from Docker Compose (`docker compose up -d
minio`) exercising put/stat/open/range/presign/delete through the same
``ObjectStorage`` interface production uses against Cloudflare R2. No cloud
credentials, subscriptions, or internet access are required.
"""

import asyncio
import io
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services.storage_service import (
    FileTooLargeError,
    build_storage_key,
    retention_deadline,
    sanitize_filename,
    sniff_mime,
    spool_upload,
)
from app.storage import (
    MinIOStorage,
    ObjectNotFoundError,
    ObjectStream,
    R2Storage,
    RangeNotSatisfiableError,
    StorageConfigError,
    build_storage,
)
from tests.conftest import skip_without_minio

# Strong secrets so production-shaped Settings pass the production validators.
_PROD_SECRETS: dict[str, Any] = {
    "secret_key": "x" * 48,
    "livekit_api_key": "real-api-key",
    "livekit_api_secret": "y" * 48,
}


class TestProviderSelection:
    """D24 §4: environment selects the provider; misconfig fails clearly."""

    def test_defaults_to_minio(self) -> None:
        storage = build_storage(Settings(_env_file=None))
        assert isinstance(storage, MinIOStorage)
        assert storage.name == "minio"

    def test_unknown_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, storage_provider="s3")

    def test_r2_requires_credentials(self) -> None:
        cfg = Settings(_env_file=None, storage_provider="r2")
        with pytest.raises(StorageConfigError, match="R2_ACCOUNT_ID"):
            build_storage(cfg)

    def test_r2_with_credentials_builds_cloud_endpoint(self) -> None:
        cfg = Settings(
            _env_file=None,
            storage_provider="r2",
            r2_account_id="acct123",
            r2_access_key_id="key-id",
            r2_secret_access_key="key-secret",
            r2_bucket="procto-evidence",
        )
        storage = build_storage(cfg)
        assert isinstance(storage, R2Storage)
        assert storage.name == "r2"
        assert storage._endpoint_url == "https://acct123.r2.cloudflarestorage.com"

    def test_production_requires_r2(self) -> None:
        cfg = Settings(
            _env_file=None, app_env="production", storage_provider="minio", **_PROD_SECRETS
        )
        with pytest.raises(StorageConfigError, match="r2"):
            build_storage(cfg)

    def test_production_with_r2_is_valid(self) -> None:
        cfg = Settings(
            _env_file=None,
            app_env="production",
            storage_provider="r2",
            r2_account_id="acct123",
            r2_access_key_id="key-id",
            r2_secret_access_key="key-secret",
            r2_bucket="procto-evidence",
            **_PROD_SECRETS,
        )
        assert build_storage(cfg).name == "r2"

    def test_empty_minio_endpoint_rejected(self) -> None:
        cfg = Settings(_env_file=None, minio_endpoint="   ")
        with pytest.raises(StorageConfigError, match="MINIO_ENDPOINT"):
            build_storage(cfg)


class TestValidationHelpers:
    """Pure helpers — content sniffing decides what a file really is."""

    @pytest.mark.parametrize(
        ("head", "expected"),
        [
            (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png"),
            (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
            (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
            (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "application/pdf"),
            (b"\x1a\x45\xdf\xa3" + b"\x00" * 12, "video/webm"),
            (b"\x00\x00\x00\x1cftypisom" + b"\x00" * 8, "video/mp4"),
            (b"just text no magic", None),
            (b"", None),
        ],
    )
    def test_sniff_mime(self, head: bytes, expected: str | None) -> None:
        assert sniff_mime(head) == expected

    def test_storage_key_is_provider_private(self) -> None:
        meeting_id = uuid.uuid4()
        file_id = uuid.uuid4()
        key = build_storage_key(meeting_id, "evidence_clip", file_id, "video/webm")
        assert key == f"meetings/{meeting_id}/evidence_clip/{file_id}.webm"
        assert "http" not in key

    def test_sanitize_filename_strips_paths_and_controls(self) -> None:
        assert sanitize_filename("../../../etc/passwd") == "passwd"
        assert sanitize_filename("C:\\temp\\evil\r\nname.png") == "evilname.png"
        assert sanitize_filename("") is None
        assert sanitize_filename(None) is None
        assert sanitize_filename("a" * 500) == "a" * 255

    def test_retention_deadline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        at = datetime(2026, 1, 1, tzinfo=UTC)
        monkeypatch.setattr(settings, "storage_retention_days", 30)
        assert retention_deadline(at) == datetime(2026, 1, 31, tzinfo=UTC)
        monkeypatch.setattr(settings, "storage_retention_days", 0)
        assert retention_deadline(at) is None

    async def test_spool_enforces_size_cap(self) -> None:
        upload = UploadFile(file=io.BytesIO(b"x" * 4096), filename="big.bin")
        with pytest.raises(FileTooLargeError):
            await spool_upload(upload, max_bytes=1024)

    async def test_spool_returns_path_size_and_head(self) -> None:
        payload = b"\x89PNG\r\n\x1a\n" + b"body" * 100
        upload = UploadFile(file=io.BytesIO(payload), filename="img.png")
        path, size, head = await spool_upload(upload, max_bytes=1024)
        try:
            assert size == len(payload)
            assert head == payload[:16]
            with open(path, "rb") as fh:
                assert fh.read() == payload
        finally:
            os.unlink(path)


@pytest.fixture
async def storage() -> AsyncIterator[MinIOStorage]:
    """Real MinIO provider (local Docker) with the bucket ensured."""
    await skip_without_minio()
    store = build_storage(settings)
    assert isinstance(store, MinIOStorage)
    await store.ensure_bucket()
    yield store


async def _drain(stream: ObjectStream) -> bytes:
    return b"".join([chunk async for chunk in stream.chunks])


class TestMinIOIntegration:
    """Provider behaviour against the real local MinIO (D24 Phase A)."""

    async def test_ensure_bucket_is_idempotent(self, storage: MinIOStorage) -> None:
        await storage.ensure_bucket()
        await storage.ensure_bucket()

    async def test_put_stat_exists_open_roundtrip(self, storage: MinIOStorage) -> None:
        payload = b"evidence-" + uuid.uuid4().bytes * 8
        key = f"tests/{uuid.uuid4()}.bin"

        await storage.put(key, io.BytesIO(payload), content_type="application/octet-stream")

        stat = await storage.stat(key)
        assert stat is not None
        assert stat.size == len(payload)
        assert stat.content_type == "application/octet-stream"
        assert await storage.exists(key) is True

        stream = await storage.open(key)
        assert stream.status == 200
        assert await _drain(stream) == payload

    async def test_open_closed_range_returns_slice(self, storage: MinIOStorage) -> None:
        payload = bytes(range(256)) * 4
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(payload), content_type="application/octet-stream")

        stream = await storage.open(key, byte_range=(10, 25))
        assert stream.status == 206
        assert await _drain(stream) == payload[10:26]
        assert stream.content_range == f"bytes 10-25/{len(payload)}"

    async def test_open_ended_range(self, storage: MinIOStorage) -> None:
        payload = b"0123456789" * 10
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(payload), content_type="application/octet-stream")

        stream = await storage.open(key, byte_range=(95, None))
        assert stream.status == 206
        assert await _drain(stream) == payload[95:]
        assert stream.content_range == f"bytes 95-{len(payload) - 1}/{len(payload)}"

    async def test_missing_object_is_none_or_not_found(self, storage: MinIOStorage) -> None:
        key = f"tests/missing-{uuid.uuid4()}"
        assert await storage.stat(key) is None
        assert await storage.exists(key) is False
        with pytest.raises(ObjectNotFoundError):
            await storage.open(key)

    async def test_range_outside_object_rejected(self, storage: MinIOStorage) -> None:
        payload = b"tiny"
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(payload), content_type="application/octet-stream")

        with pytest.raises(RangeNotSatisfiableError):
            await storage.open(key, byte_range=(1000, 2000))

    async def test_delete_is_idempotent(self, storage: MinIOStorage) -> None:
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(b"bye"), content_type="application/octet-stream")

        await storage.delete(key)
        await storage.delete(key)  # deleting a missing key must not raise

        assert await storage.stat(key) is None

    async def test_presigned_url_serves_object(self, storage: MinIOStorage) -> None:
        payload = b"signed-" + uuid.uuid4().bytes
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(payload), content_type="application/octet-stream")

        url = storage.presign_get(key, expires_in=60)
        assert "X-Amz-Expires=60" in url

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        assert response.status_code == 200
        assert response.content == payload

    async def test_presigned_url_expires(self, storage: MinIOStorage) -> None:
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(b"secret"), content_type="application/octet-stream")

        url = storage.presign_get(key, expires_in=1)
        await asyncio.sleep(1.3)

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        assert response.status_code == 403

    async def test_unauthorized_client_cannot_fetch(self, storage: MinIOStorage) -> None:
        key = f"tests/{uuid.uuid4()}.bin"
        await storage.put(key, io.BytesIO(b"private"), content_type="application/octet-stream")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:9000/procto/{key}")

        assert response.status_code == 403
