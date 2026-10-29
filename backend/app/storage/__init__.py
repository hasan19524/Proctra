"""Object storage entry point (DECISIONS.md D24).

``STORAGE_PROVIDER`` selects the implementation — ``minio`` for local
development/testing, ``r2`` for Cloudflare R2, or the generic ``s3`` profile
(Backblaze B2, Wasabi, ...) in cloud production — and the rest of the
application only ever imports the ABC from this package.

Configuration is validated eagerly (:func:`build_storage`), so a misconfigured
deployment fails clearly at startup instead of erroring on the first upload:

* ``STORAGE_PROVIDER=r2`` without the ``R2_*`` credentials → error naming each
  missing variable.
* ``STORAGE_PROVIDER=s3`` without the ``S3_*`` values → error naming each
  missing variable.
* ``STORAGE_PROVIDER=minio`` in production → error (production must use R2 or
  a generic S3-compatible store).
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
from app.storage.s3 import MinIOStorage, R2Storage, S3Storage

__all__ = [
    "MinIOStorage",
    "ObjectNotFoundError",
    "ObjectStat",
    "ObjectStorage",
    "ObjectStream",
    "R2Storage",
    "RangeNotSatisfiableError",
    "S3Storage",
    "StorageConfigError",
    "StorageError",
    "StorageUnavailableError",
    "build_storage",
    "get_storage",
    "reset_storage_cache",
    "storage_dep",
]


def _require(cfg: Settings, pairs: tuple[tuple[str, str], ...], provider: str, hint: str) -> None:
    """Fail fast, naming every missing variable at once (D24 §4)."""
    missing = [label for label, value in pairs if not value.strip()]
    if missing:
        raise StorageConfigError(
            f"STORAGE_PROVIDER={provider} but storage is not configured: missing "
            + ", ".join(missing)
            + f". {hint}"
        )


def build_storage(cfg: Settings) -> ObjectStorage:
    """Construct the provider named by ``cfg`` — pure, so tests can drive it."""
    if cfg.storage_provider == "r2":
        _require(
            cfg,
            (
                ("R2_ACCOUNT_ID", cfg.r2_account_id),
                ("R2_ACCESS_KEY_ID", cfg.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", cfg.r2_secret_access_key),
                ("R2_BUCKET", cfg.r2_bucket),
            ),
            provider="r2",
            hint="Set the Cloudflare R2 credentials or switch "
            "STORAGE_PROVIDER=minio for local development.",
        )
        return R2Storage(
            account_id=cfg.r2_account_id.strip(),
            access_key_id=cfg.r2_access_key_id.strip(),
            secret_access_key=cfg.r2_secret_access_key.strip(),
            bucket=cfg.r2_bucket.strip(),
        )

    if cfg.storage_provider == "s3":
        _require(
            cfg,
            (
                ("S3_ENDPOINT", cfg.s3_endpoint),
                ("S3_REGION", cfg.s3_region),
                ("S3_ACCESS_KEY_ID", cfg.s3_access_key_id),
                ("S3_SECRET_ACCESS_KEY", cfg.s3_secret_access_key),
                ("S3_BUCKET", cfg.s3_bucket),
            ),
            provider="s3",
            hint="Set the S3-compatible endpoint/credentials (e.g. Backblaze B2) "
            "or switch STORAGE_PROVIDER=minio for local development.",
        )
        return S3Storage(
            endpoint=cfg.s3_endpoint.strip(),
            access_key_id=cfg.s3_access_key_id.strip(),
            secret_access_key=cfg.s3_secret_access_key.strip(),
            bucket=cfg.s3_bucket.strip(),
            region=cfg.s3_region.strip(),
            addressing_style=cfg.s3_addressing_style,
        )

    # STORAGE_PROVIDER=minio
    if cfg.is_production:
        raise StorageConfigError(
            "STORAGE_PROVIDER=minio is not allowed in production: object storage "
            "must use a cloud S3-compatible store — set STORAGE_PROVIDER=s3 with "
            "S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and "
            "S3_BUCKET (e.g. Backblaze B2), or STORAGE_PROVIDER=r2 with the "
            "R2_* credentials (Cloudflare R2)."
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
