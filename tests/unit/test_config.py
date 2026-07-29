from pathlib import Path

from nora.infrastructure.config import Environment, Settings


def test_settings_load_dotenv_and_convert_types(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENV=staging\nDEBUG=true\nLOG_LEVEL=warning\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.env is Environment.STAGING
    assert settings.debug is True
    assert settings.log_level == "warning"


def test_environment_variables_override_dotenv(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENV=staging\nDEBUG=false\n", encoding="utf-8")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DEBUG", "true")

    settings = Settings(_env_file=env_file)

    assert settings.env is Environment.PROD
    assert settings.debug is True
