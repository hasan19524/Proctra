"""Object storage entry point (DECISIONS.md D24).

``STORAGE_PROVIDER`` selects the implementation — ``minio`` for local
development/testing and ``r2`` for Cloudflare R2 in cloud production — and the
rest of the application only ever imports the ABC from this package.

Configuration is validated eagerly (:func:`build_storage`), so a misconfigured
deployment fails clearly at startup instead of erroring on the first upload:

* ``STORAGE_PROVIDER=r2`` without the ``R2_*`` credentials → error naming each
  missing variable.
* ``STORAGE_PROVIDER=minio`` in production → error (production must use R2).
* An unknown provider is rejected by the typed ``Settings.storage_provider``
  field itself.
"""

from collections.abc import Callable

from app.core.config import Settings, settings
from app.storage.base import (
    ObjectNotFoundError,
    ObjectStat,
    ObjectStorage,
    ObjectStream,
    RangeNotSatisfiableError,
    StorageConfigError,
    StorageError,
    StorageUnavailableError,
)
from app.storage.s3 import MinIOStorage, R2Storage

__all__ = [
    "MinIOStorage",
    "ObjectNotFoundError",
    "ObjectStat",
    "ObjectStorage",
    "ObjectStream",
    "R2Storage",
    "RangeNotSatisfiableError",
    "StorageConfigError",
    "StorageError",
    "StorageUnavailableError",
    "build_storage",
    "get_storage",
    "reset_storage_cache",
    "storage_dep",
]


def build_storage(cfg: Settings) -> ObjectStorage:
    """Construct the provider named by ``cfg`` — pure, so tests can drive it."""
    if cfg.storage_provider == "r2":
        missing = [
            label
            for label, value in (
                ("R2_ACCOUNT_ID", cfg.r2_account_id),
                ("R2_ACCESS_KEY_ID", cfg.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", cfg.r2_secret_access_key),
                ("R2_BUCKET", cfg.r2_bucket),
            )
            if not value.strip()
        ]
        if missing:
            raise StorageConfigError(
                "STORAGE_PROVIDER=r2 but storage is not configured: missing "
                + ", ".join(missing)
                + ". Set the Cloudflare R2 credentials or switch "
                "STORAGE_PROVIDER=minio for local development."
            )
        return R2Storage(
            account_id=cfg.r2_account_id.strip(),
            access_key_id=cfg.r2_access_key_id.strip(),
            secret_access_key=cfg.r2_secret_access_key.strip(),
            bucket=cfg.r2_bucket.strip(),
        )

    # STORAGE_PROVIDER=minio
    if cfg.is_production:
        raise StorageConfigError(
            "STORAGE_PROVIDER=minio is not allowed in production: object storage "
            "must use Cloudflare R2 (set STORAGE_PROVIDER=r2 together with "
            "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET)."
        )
    if not cfg.minio_endpoint.strip():
        raise StorageConfigError(
            "STORAGE_PROVIDER=minio but MINIO_ENDPOINT is empty. Start the local "
            "MinIO service (docker compose up -d minio) or configure R2."
        )
    return MinIOStorage(
        endpoint=cfg.minio_endpoint.strip(),
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
        bucket=cfg.minio_bucket,
        secure=cfg.minio_secure,
    )


_cached: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    """Process-wide storage singleton (validated once, then reused)."""
    global _cached
    if _cached is None:
        _cached = build_storage(settings)
    return _cached


def reset_storage_cache() -> None:
    """Drop the singleton (tests that swap configuration)."""
    global _cached
    _cached = None


def storage_dep() -> ObjectStorage:
    """FastAPI dependency yielding the configured provider (overridable in tests)."""
    return get_storage()


# Typing alias for routes: dependencies are plain callables returning the ABC.
StorageDependency = Callable[[], ObjectStorage]
