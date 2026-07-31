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

    settings = Settings(_env_file=env_file)

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
