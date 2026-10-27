"""Configuration unit tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Valid production-grade secrets so the production validator passes.
_PROD_SECRETS = {
    "secret_key": "x" * 48,
    "livekit_api_key": "real-api-key",
    "livekit_api_secret": "y" * 48,
}


def test_cors_origins_accept_comma_separated_string() -> None:
    settings = Settings(
        _env_file=None,
        backend_cors_origins="http://localhost:3000, http://127.0.0.1:3000",
    )
    assert settings.backend_cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_accept_json_list() -> None:
    settings = Settings(_env_file=None, backend_cors_origins='["http://localhost:3000"]')
    assert settings.backend_cors_origins == ["http://localhost:3000"]


def test_production_flag() -> None:
    assert Settings(_env_file=None, app_env="production", **_PROD_SECRETS).is_production
    assert not Settings(_env_file=None, app_env="development").is_production


def test_production_rejects_dev_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", secret_key="insecure-dev-key-change-me")


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="short",
            **{k: v for k, v in _PROD_SECRETS.items() if k != "secret_key"},
        )


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", app_debug=True, **_PROD_SECRETS)


def test_production_rejects_dev_livekit_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            livekit_api_secret="procto-dev-secret",
            secret_key=_PROD_SECRETS["secret_key"],
            livekit_api_key="real-api-key",
        )


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, backend_cors_origins="*")


def test_cors_rejects_non_http_origin() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, backend_cors_origins="ftp://example.com")


def test_jwt_algorithm_allowlist_rejects_none() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_algorithm="none")


def test_jwt_algorithm_allowlist_accepts_hs256() -> None:
    assert Settings(_env_file=None, jwt_algorithm="HS256").jwt_algorithm == "HS256"


def test_trusted_hosts_defaults_empty() -> None:
    assert Settings(_env_file=None).trusted_hosts == []
