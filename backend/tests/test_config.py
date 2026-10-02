"""Configuration unit tests."""

from app.core.config import Settings


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
    assert Settings(_env_file=None, app_env="production").is_production
    assert not Settings(_env_file=None, app_env="development").is_production
