"""Provider-independent object storage contract (DECISIONS.md D24).

Business logic (uploads, evidence reads, retention, reports) talks only to
:class:`ObjectStorage`. Two S3-compatible providers implement it —
``MinIOStorage`` for local development/testing and ``R2Storage`` for Cloudflare
R2 in production — and nothing outside ``app.storage`` ever learns which one is
configured (``STORAGE_PROVIDER``).

Every method is async; blocking SDK calls run in a worker thread so storage I/O
never stalls the event loop. Errors surface as a small closed hierarchy so API
routes can map them to accurate HTTP statuses (404 missing, 416 bad range,
503 storage down) without inspecting provider-specific exceptions.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import IO, BinaryIO


class StorageError(RuntimeError):
    """Storage operation failed for a reason other than a missing object."""


class StorageConfigError(StorageError):
    """Configuration is missing/invalid — raised at startup, never at request time."""


class ObjectNotFoundError(StorageError):
    """The requested object does not exist (mapped to HTTP 404)."""


class RangeNotSatisfiableError(StorageError):
    """The requested byte range is outside the object (mapped to HTTP 416)."""


class StorageUnavailableError(StorageError):
    """The storage backend could not be reached (mapped to HTTP 503)."""


@dataclass(frozen=True)
class ObjectStat:
    """Metadata about a stored object (no provider URLs — keys only)."""

    size: int
    content_type: str
    etag: str | None = None


@dataclass(frozen=True)
class ObjectStream:
    """A successful object read: status + metadata + an async byte stream."""

    status: int  # 200 (full) or 206 (partial content)
    content_type: str
    size: int | None  # total object size when known
    content_range: str | None  # e.g. "bytes 0-99/4321" on 206 responses
    chunks: AsyncIterator[bytes]


class ObjectStorage(ABC):
    """The operations Procto needs from any object store (D24 §3)."""

    #: Provider name for diagnostics ("minio" / "r2").
    name: str

    @abstractmethod
    async def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not exist yet (idempotent)."""

    @abstractmethod
    async def put(
        self,
        key: str,
        fileobj: "IO[bytes] | BinaryIO",
        *,
        content_type: str,
        length: int | None = None,
    ) -> None:
        """Upload an object. Large bodies may use multipart internally."""

    @abstractmethod
    async def stat(self, key: str) -> ObjectStat | None:
        """Object metadata, or ``None`` when the object does not exist."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Whether the object is present."""

    @abstractmethod
    async def open(
        self, key: str, *, byte_range: tuple[int, int | None] | None = None
    ) -> ObjectStream:
        """Open an object for streaming (optionally a ``[start, end]`` range).

        ``end`` may be ``None`` for an open-ended range (``bytes=start-``).
        Raises :class:`ObjectNotFoundError` when the key is absent and
        :class:`RangeNotSatisfiableError` when the range lies outside the object.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object; deleting a missing key is a no-op (idempotent)."""

    @abstractmethod
    def presign_get(self, key: str, *, expires_in: int) -> str:
        """Short-lived signed GET URL (local computation — no I/O, no network)."""
