"""Production deployment preflight contracts."""

import importlib.util
from pathlib import Path

import pytest

PREFLIGHT_PATH = Path(__file__).parents[3] / "deploy" / "preflight.py"
SPEC = importlib.util.spec_from_file_location("nora_production_preflight", PREFLIGHT_PATH)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)
read_environment = PREFLIGHT.read_environment
validate_environment = PREFLIGHT.validate_environment
validate_database_identities = PREFLIGHT._validate_database_identities
DEPLOY_DIR = Path(__file__).parents[3] / "deploy"


def _values() -> dict[str, str]:
    digest = "0" * 64
    return {
        "NORA_API_IMAGE": f"ghcr.io/dev-cai/nora-api@sha256:{digest}",
        "NORA_WEB_IMAGE": f"ghcr.io/dev-cai/nora-web@sha256:{digest}",
        "NORA_PROVIDER": "provider-a",
        "NORA_REGION": "region-a",
        "NORA_BACKUP_DESTINATION_ID": "private-backup-a",
        "NORA_MONTHLY_BUDGET": "100 CNY",
        "NORA_BUDGET_ALERT": "80 CNY",
        "NORA_PUBLIC_ORIGIN": "https://nora.internal.test",
        "NORA_WEB_PORT": "18080",
        "NORA_DATABASE_URL_FILE": "/secrets/database-url",
        "NORA_DATABASE_ADMIN_URL_FILE": "/secrets/database-admin-url",
        "NORA_POSTGRES_PASSWORD_FILE": "/secrets/postgres-password",
        "NORA_POSTGRES_APP_PASSWORD_FILE": "/secrets/postgres-app-password",
        "NORA_AUTH_RATE_LIMIT_SECRET_FILE": "/secrets/auth-rate",
        "NORA_ARTIFACT_ACCESS_KEY_FILE": "/secrets/artifact-access",
        "NORA_ARTIFACT_SECRET_KEY_FILE": "/secrets/artifact-secret",
        "NORA_MINIO_ROOT_USER_FILE": "/secrets/minio-user",
        "NORA_MINIO_ROOT_PASSWORD_FILE": "/secrets/minio-password",
        "NORA_ARTIFACT_BACKUP_ACCESS_KEY_FILE": "/secrets/backup-access",
        "NORA_ARTIFACT_BACKUP_SECRET_KEY_FILE": "/secrets/backup-secret",
        "NORA_JWT_KEY_RING_DIR": "/secrets/jwt",
        "NORA_POSTGRES_DATA_DIR": "/data/postgres",
        "NORA_MINIO_DATA_DIR": "/data/minio",
        "NORA_BACKUP_STAGE_DIR": "/data/stage",
    }


def test_config_preflight_accepts_digest_pins_and_real_environment_record() -> None:
    assert validate_environment(_values(), check_host=False) == []


def test_config_preflight_rejects_mutable_images_direct_secrets_and_placeholder_target() -> None:
    values = _values() | {
        "NORA_API_IMAGE": "ghcr.io/dev-cai/nora-api:latest",
        "DATABASE_URL": "postgresql+asyncpg://nora:secret@db/nora",
        "NORA_PROVIDER": "UNSET",
        "NORA_PUBLIC_ORIGIN": "http://nora.example.com",
    }

    errors = validate_environment(values, check_host=False)

    assert any("DATABASE_URL" in error for error in errors)
    assert any("NORA_API_IMAGE" in error for error in errors)
    assert any("NORA_PROVIDER" in error for error in errors)
    assert any("valid HTTPS origin" in error for error in errors)


def test_environment_reader_preserves_structured_values(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "# comment\nNORA_PROVIDER=provider a\nNORA_REGION='cn north'\n", encoding="utf-8"
    )

    assert read_environment(env_file) == {
        "NORA_PROVIDER": "provider a",
        "NORA_REGION": "cn north",
    }


def test_environment_reader_rejects_invalid_or_duplicate_names(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.env"
    invalid.write_text("NORA_PROVIDER=provider-a\nBAD-NAME=value\n", encoding="utf-8")
    duplicate = tmp_path / "duplicate.env"
    duplicate.write_text("NORA_PROVIDER=a\nNORA_PROVIDER=b\n", encoding="utf-8")

    for env_file in (invalid, duplicate):
        try:
            read_environment(env_file)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe environment input must be rejected")


def test_environment_reader_rejects_web_port_whitespace_or_non_digits(tmp_path: Path) -> None:
    for value in (" 18080", "18080 ", "+18080", "18080.0", "'18080'"):
        env_file = tmp_path / "production.env"
        env_file.write_text(f"NORA_WEB_PORT={value}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="NORA_WEB_PORT"):
            read_environment(env_file)


@pytest.mark.parametrize(
    "origin",
    [
        "http://nora.internal.test",
        "https://localhost",
        "https://nora.example.com",
        "https://127.0.0.1",
        "https://user:pass@nora.internal.test",
        "https://nora.internal.test/path",
        "https://nora.internal.test?query=1",
        "https://nora.internal.test#fragment",
        "https://invalid_host.internal",
        "https://invalid host.internal",
        "https://invalid\\host.internal",
    ],
)
def test_config_preflight_rejects_invalid_public_origins(origin: str) -> None:
    errors = validate_environment(_values() | {"NORA_PUBLIC_ORIGIN": origin}, check_host=False)
    assert any("NORA_PUBLIC_ORIGIN" in error for error in errors)


@pytest.mark.parametrize("port", ["", "-1", "0", "80", "65536", "1.5", "not-a-port"])
def test_config_preflight_rejects_invalid_web_ports(port: str) -> None:
    errors = validate_environment(_values() | {"NORA_WEB_PORT": port}, check_host=False)
    assert any("NORA_WEB_PORT" in error for error in errors)


def test_root_operator_scripts_do_not_source_environment_files() -> None:
    for script_name in ("backup.sh", "restore.sh"):
        script = (DEPLOY_DIR / script_name).read_text(encoding="utf-8")
        assert '. "$env_file"' not in script
        assert '--get "$1"' in script


def test_database_identity_preflight_requires_distinct_matching_credentials(
    tmp_path: Path,
) -> None:
    paths = {
        "NORA_DATABASE_URL_FILE": tmp_path / "database-url",
        "NORA_DATABASE_ADMIN_URL_FILE": tmp_path / "database-admin-url",
        "NORA_POSTGRES_PASSWORD_FILE": tmp_path / "postgres-password",
        "NORA_POSTGRES_APP_PASSWORD_FILE": tmp_path / "postgres-app-password",
    }
    paths["NORA_DATABASE_URL_FILE"].write_text(
        "postgresql+asyncpg://nora_app:app%2Fsecret@db/nora", encoding="utf-8"
    )
    paths["NORA_DATABASE_ADMIN_URL_FILE"].write_text(
        "postgresql+asyncpg://nora_admin:admin%2Fsecret@db/nora", encoding="utf-8"
    )
    paths["NORA_POSTGRES_PASSWORD_FILE"].write_text("admin/secret", encoding="utf-8")
    paths["NORA_POSTGRES_APP_PASSWORD_FILE"].write_text("app/secret", encoding="utf-8")
    values = {"NORA_POSTGRES_ADMIN_USER": "nora_admin", "NORA_POSTGRES_APP_USER": "nora_app"}

    assert validate_database_identities(values, paths) == []

    paths["NORA_DATABASE_URL_FILE"].write_text(
        "postgresql+asyncpg://nora_admin:admin%2Fsecret@db/nora", encoding="utf-8"
    )
    errors = validate_database_identities(values, paths)

    assert any("runtime user" in error for error in errors)
    assert any("application password" in error for error in errors)
