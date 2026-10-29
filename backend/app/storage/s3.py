"""S3-compatible storage providers: MinIO (dev/test), Cloudflare R2, and a
generic endpoint-described profile (Backblaze B2, Wasabi, ...) for production.

All providers speak the S3 wire protocol, so they share one implementation
(``S3CompatibleStorage``) and differ only in endpoint/addressing configuration:

* ``MinIOStorage`` — plain ``http://`` endpoint on localhost, path-style keys
  (``/bucket/key``), self-hosted via Docker Compose. Never needs internet.
* ``R2Storage`` — Cloudflare's virtual-hosted S3 endpoint
  (``https://<account>.r2.cloudflarestorage.com``), region ``auto``.
* ``S3Storage`` — fully configuration-described S3-compatible endpoint
  (Backblaze B2, Wasabi, DigitalOcean Spaces, ...) with an explicit
  endpoint/region and path-style addressing by default.

boto3 calls are synchronous; every public method offloads to a worker thread
(``run_in_threadpool``) so storage I/O never blocks the event loop. The boto3
client itself is thread-confined (botocore clients are not thread-safe), so a
fresh client is cached per thread on first use.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from typing import IO, Any, BinaryIO, NoReturn

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    ReadTimeoutError,
)
from starlette.concurrency import run_in_threadpool

from app.storage.base import (
    ObjectNotFoundError,
    ObjectStat,
    ObjectStorage,
    ObjectStream,
    RangeNotSatisfiableError,
    StorageError,
    StorageUnavailableError,
)

# Stream chunk size for proxied reads (keeps memory flat for big objects).
_CHUNK_BYTES = 64 * 1024

# ClientError codes that mean "object does not exist".
_MISSING_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NotFound", "404", "NoSuchBucket"})

# Transport-level failures (backend unreachable) → StorageUnavailableError.
_CONN_ERRORS = (
    EndpointConnectionError,
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionClosedError,
    HTTPClientError,
    ConnectionError,
    OSError,
)


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _is_missing(exc: ClientError) -> bool:
    """True when a ClientError means the key/bucket simply is not there."""
    if _error_code(exc) in _MISSING_CODES:
        return True
    status: int = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    return status == 404


def _total_from_content_range(value: str | None) -> int | None:
    """Parse the total size out of ``Content-Range: bytes 0-99/4321``."""
    if not value or "/" not in value:
        return None
    total = value.rsplit("/", 1)[1].strip()
    return int(total) if total.isdigit() else None


class S3CompatibleStorage(ObjectStorage):
    """Shared S3-protocol implementation behind both concrete providers."""

    name = "s3"

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
        addressing_style: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._addressing_style = addressing_style
        self._tls = threading.local()

    # ------------------------------------------------------------------ client
    def _client(self) -> BaseClient:
        """One botocore client per thread (thread-confined, reused via a pool)."""
        client = getattr(self._tls, "client", None)
        if client is None:
            client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": self._addressing_style},
                    connect_timeout=5,
                    read_timeout=60,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            self._tls.client = client
        return client

    @staticmethod
    def _raise_mapped(exc: Exception, *, op: str) -> NoReturn:
        """Translate boto exceptions into the storage error hierarchy."""
        if isinstance(exc, ClientError):
            if _error_code(exc) == "InvalidRange":
                raise RangeNotSatisfiableError(f"{op}: requested range outside object") from exc
            if _is_missing(exc):
                raise ObjectNotFoundError(f"{op}: object not found") from exc
            raise StorageError(f"{op} failed: {_error_code(exc)}") from exc
        if isinstance(exc, _CONN_ERRORS):
            raise StorageUnavailableError(f"{op}: storage backend unreachable") from exc
        if isinstance(exc, (StorageError,)):
            raise
        raise StorageError(f"{op} failed: {exc!r}") from exc

    # ----------------------------------------------------------------- bucket
    async def ensure_bucket(self) -> None:
        """Create the bucket if absent (idempotent; races tolerated)."""

        def _ensure() -> None:
            client = self._client()
            try:
                client.head_bucket(Bucket=self._bucket)
                return
            except ClientError:
                pass
            try:
                client.create_bucket(Bucket=self._bucket)
            except ClientError as exc:
                code = _error_code(exc)
                if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    return
                raise

        try:
            await run_in_threadpool(_ensure)
        except Exception as exc:
            self._raise_mapped(exc, op="ensure_bucket")

    # ------------------------------------------------------------------- put
    async def put(
        self,
        key: str,
        fileobj: IO[bytes] | BinaryIO,
        *,
        content_type: str,
        length: int | None = None,
    ) -> None:
        """Upload via ``upload_fileobj`` (switches to multipart above 8 MiB)."""

        def _put() -> None:
            self._client().upload_fileobj(
                fileobj,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )

        try:
            await run_in_threadpool(_put)
        except Exception as exc:
            self._raise_mapped(exc, op=f"put({key})")

    # ------------------------------------------------------------------ stat
    async def stat(self, key: str) -> ObjectStat | None:
        def _head() -> dict[str, Any]:
            resp: dict[str, Any] = self._client().head_object(Bucket=self._bucket, Key=key)
            return resp

        try:
            resp = await run_in_threadpool(_head)
        except Exception as exc:
            if isinstance(exc, ClientError) and _is_missing(exc):
                return None
            self._raise_mapped(exc, op=f"stat({key})")
        return ObjectStat(
            size=int(resp["ContentLength"]),
            content_type=str(resp.get("ContentType") or "application/octet-stream"),
            etag=str(resp.get("ETag")) if resp.get("ETag") else None,
        )

    async def exists(self, key: str) -> bool:
        return await self.stat(key) is not None

    # ------------------------------------------------------------------ open
    async def open(
        self, key: str, *, byte_range: tuple[int, int | None] | None = None
    ) -> ObjectStream:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if byte_range is not None:
            start, end = byte_range
            params["Range"] = f"bytes={start}-{'' if end is None else end}"

        def _get() -> dict[str, Any]:
            resp: dict[str, Any] = self._client().get_object(**params)
            return resp

        try:
            resp = await run_in_threadpool(_get)
        except Exception as exc:
            self._raise_mapped(exc, op=f"open({key})")

        body = resp["Body"]  # botocore StreamingBody (sync reads → threadpool)
        content_type = str(resp.get("ContentType") or "application/octet-stream")
        content_range = resp.get("ContentRange")
        status: int
        size: int | None
        if byte_range is None:
            status, size = 200, int(resp["ContentLength"])
        else:
            status, size = 206, _total_from_content_range(content_range)

        async def _chunks() -> AsyncIterator[bytes]:
            try:
                while True:
                    chunk = await run_in_threadpool(body.read, _CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await run_in_threadpool(body.close)

        return ObjectStream(
            status=status,
            content_type=content_type,
            size=size,
            content_range=str(content_range) if content_range else None,
            chunks=_chunks(),
        )

    # ---------------------------------------------------------------- delete
    async def delete(self, key: str) -> None:
        def _delete() -> None:
            self._client().delete_object(Bucket=self._bucket, Key=key)

        try:
            await run_in_threadpool(_delete)  # S3 delete is 204 even when absent
        except Exception as exc:
            self._raise_mapped(exc, op=f"delete({key})")

    # ---------------------------------------------------------------- presign
    def presign_get(self, key: str, *, expires_in: int) -> str:
        """Short-lived signed GET URL — pure local HMAC, no network call."""
        url: str = self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url


class MinIOStorage(S3CompatibleStorage):
    """Local development/testing provider (D24 Phase A).

    Path-style addressing over plain HTTP on localhost — no cloud account,
    credentials subscription, or internet connection required.
    """

    name = "minio"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str = "us-east-1",
    ) -> None:
        base = endpoint if "://" in endpoint else f"{'https' if secure else 'http'}://{endpoint}"
        super().__init__(
            endpoint_url=base.rstrip("/"),
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            region=region,
            addressing_style="path",
        )


class R2Storage(S3CompatibleStorage):
    """Cloudflare R2 provider (D24 Phase B — cloud deployment/production).

    R2 exposes an S3-compatible API at ``https://<account>.r2.cloudflarestorage.com``
    with region ``auto``; credentials are server-side only and never reach the
    frontend (SECURITY.md §6).
    """

    name = "r2"

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str = "auto",
    ) -> None:
        super().__init__(
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            access_key=access_key_id,
            secret_key=secret_access_key,
            bucket=bucket,
            region=region,
            addressing_style="auto",
        )


class S3Storage(S3CompatibleStorage):
    """Generic S3-compatible provider (D24 §3.2 generalization).

    Any endpoint-addressed S3 implementation — Backblaze B2
    (``https://s3.<region>.backblazeb2.com``), Wasabi, DigitalOcean Spaces — is
    described entirely by configuration: endpoint, region, credentials, and
    addressing style. Nothing vendor-specific is hardcoded, so a new store is
    an env value rather than a code change. Path-style addressing is the
    default because every S3-compatible vendor accepts it.

    Credentials are server-side only and never reach the frontend
    (SECURITY.md §6).
    """

    name = "s3"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str,
        addressing_style: str = "path",
    ) -> None:
        base = endpoint if "://" in endpoint else f"https://{endpoint}"
        super().__init__(
            endpoint_url=base.rstrip("/"),
            access_key=access_key_id,
            secret_key=secret_access_key,
            bucket=bucket,
            region=region,
            addressing_style=addressing_style,
        )
