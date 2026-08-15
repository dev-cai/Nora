from pathlib import Path

import pytest
from app.infrastructure.config import Environment, Settings
from pydantic import ValidationError

TEST_AUTH_SECRET = "test-auth-secret-key-with-32-bytes!"


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


def test_settings_reject_non_postgresql_database_url() -> None:
    with pytest.raises(ValidationError, match=r"DATABASE_URL must use postgresql\+asyncpg"):
        Settings(database_url="sqlite:///nora.db", _env_file=None)


@pytest.mark.parametrize(
    "origin",
    ["*", "null", "http://nora.example", "https://nora.example/path", "https://nora.example?q=1"],
)
def test_production_rejects_unsafe_public_origin(tmp_path: Path, origin: str) -> None:
    key_ring = tmp_path / "keys"
    key_ring.mkdir()
    (key_ring / "active").write_text("a" * 32, encoding="utf-8")
    with pytest.raises(ValidationError, match="PUBLIC_ORIGIN"):
        Settings(
            env=Environment.PROD,
            database_url="postgresql+asyncpg://nora:nora@localhost/nora",
            auth_secret_key=TEST_AUTH_SECRET,
            auth_key_ring_directory=key_ring,
            auth_active_kid="active",
            auth_rate_limit_secret="b" * 32,
            public_origin=origin,
            trusted_proxy_cidr="10.0.0.0/8",
            _env_file=None,
        )


def test_artifact_storage_configuration_is_private_and_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.artifact_storage_endpoint == "storage:9000"
    assert "application/pdf" in settings.allowed_artifact_content_types
    with pytest.raises(ValidationError, match="host:port"):
        Settings(artifact_storage_endpoint="http://storage:9000", _env_file=None)
    with pytest.raises(ValidationError, match="bucket"):
        Settings(artifact_storage_bucket="Invalid/Bucket", _env_file=None)
