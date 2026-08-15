from pathlib import Path
from typing import Any

import pytest
from app.infrastructure.config import Environment, Settings
from app.infrastructure.config.settings import DEFAULT_AUTH_RATE_LIMIT_SECRET
from pydantic import ValidationError

TEST_AUTH_SECRET = "test-auth-secret-key-with-32-bytes!"


def _production_kwargs(tmp_path: Path) -> dict[str, Any]:
    key_ring = tmp_path / "keys"
    key_ring.mkdir(parents=True)
    (key_ring / "active").write_text("a" * 32, encoding="utf-8")
    return {
        "env": Environment.PROD,
        "database_url": "postgresql+asyncpg://nora:nora@localhost/nora",
        "auth_secret_key": TEST_AUTH_SECRET,
        "auth_key_ring_directory": key_ring,
        "auth_active_kid": "active",
        "auth_rate_limit_secret": "b" * 32,
        "public_origin": "https://nora.example",
        "trusted_proxy_cidr": "10.0.0.0/8",
        "_env_file": None,
    }


def test_settings_load_dotenv_and_convert_types(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ENV=staging\nDEBUG=true\nLOG_LEVEL=warning\nAUTH_SECRET_KEY={TEST_AUTH_SECRET}\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.env is Environment.STAGING
    assert settings.debug is True
    assert settings.log_level == "warning"


def test_environment_variables_override_dotenv(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ENV=staging\nDEBUG=false\nAUTH_SECRET_KEY={TEST_AUTH_SECRET}\n", encoding="utf-8"
    )
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DEBUG", "true")
    key_ring = tmp_path / "keys"
    key_ring.mkdir()
    (key_ring / "active").write_text("a" * 32, encoding="utf-8")

    settings = Settings(
        _env_file=env_file,
        database_url="postgresql+asyncpg://nora:nora@localhost/nora",
        auth_key_ring_directory=key_ring,
        auth_active_kid="active",
        auth_rate_limit_secret="b" * 32,
        public_origin="https://nora.example",
        trusted_proxy_cidr="10.0.0.0/8",
    )

    assert settings.env is Environment.PROD
    assert settings.debug is True


@pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PROD])
def test_non_development_environment_rejects_default_auth_secret(
    environment: Environment,
) -> None:
    with pytest.raises(ValidationError, match="AUTH_SECRET_KEY must be changed"):
        Settings(env=environment, _env_file=None)


def test_auth_configuration_rejects_weak_secret_and_invalid_lifetime() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_secret_key="too-short", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(auth_access_token_minutes=0, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(auth_access_token_minutes=31, _env_file=None)


def test_settings_reject_non_postgresql_database_url() -> None:
    with pytest.raises(ValidationError, match=r"DATABASE_URL must use postgresql\+asyncpg"):
        Settings(database_url="sqlite:///nora.db", _env_file=None)


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "*",
        "null",
        "http://nora.example",
        "https://nora.example/path",
        "https://nora.example?q=1",
    ],
)
def test_production_rejects_unsafe_public_origin(tmp_path: Path, origin: str | None) -> None:
    with pytest.raises(ValidationError, match="PUBLIC_ORIGIN"):
        Settings(**(_production_kwargs(tmp_path) | {"public_origin": origin}))


@pytest.mark.parametrize("proxy", [None, "0.0.0.0/0", "203.0.113.0/24"])
def test_production_rejects_missing_or_public_trusted_proxy(
    tmp_path: Path, proxy: str | None
) -> None:
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_CIDR"):
        Settings(**(_production_kwargs(tmp_path) | {"trusted_proxy_cidr": proxy}))


def test_production_rejects_unsafe_authentication_secrets(tmp_path: Path) -> None:
    default_rate_secret = _production_kwargs(tmp_path)
    default_rate_secret["auth_rate_limit_secret"] = DEFAULT_AUTH_RATE_LIMIT_SECRET
    with pytest.raises(ValidationError, match="AUTH_RATE_LIMIT_SECRET must be changed"):
        Settings(**default_rate_secret)

    reused_rate_secret = _production_kwargs(tmp_path / "reused")
    reused_rate_secret["auth_rate_limit_secret"] = "a" * 32
    with pytest.raises(ValidationError, match="separate from JWT keys"):
        Settings(**reused_rate_secret)


def test_production_rejects_missing_active_or_weak_key(tmp_path: Path) -> None:
    missing_active = _production_kwargs(tmp_path)
    missing_active["auth_active_kid"] = "missing"
    with pytest.raises(ValidationError, match="identify a configured JWT key"):
        Settings(**missing_active)

    weak_key = _production_kwargs(tmp_path / "weak")
    key_ring = weak_key["auth_key_ring_directory"]
    assert isinstance(key_ring, Path)
    (key_ring / "active").write_text("too-short", encoding="utf-8")
    with pytest.raises(ValidationError, match="JWT keys must contain at least 32 bytes"):
        Settings(**weak_key)


def test_artifact_storage_configuration_is_private_and_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.artifact_storage_endpoint == "storage:9000"
    assert "application/pdf" in settings.allowed_artifact_content_types
    with pytest.raises(ValidationError, match="host:port"):
        Settings(artifact_storage_endpoint="http://storage:9000", _env_file=None)
    with pytest.raises(ValidationError, match="bucket"):
        Settings(artifact_storage_bucket="Invalid/Bucket", _env_file=None)
