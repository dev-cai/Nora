"""PostgreSQL production role input safety tests."""

from pathlib import Path

import pytest
from scripts import init_postgres_role
from scripts.init_postgres_role import _quoted_identifier, _quoted_literal


class _ExistingRoleConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def fetchval(self, query: str, *_args: object) -> object:
        if "pg_roles" in query:
            return True
        return "nora"

    async def execute(self, statement: str) -> None:
        self.statements.append(statement)

    async def close(self) -> None:
        return None


def test_postgres_role_identifier_is_fixed_and_password_is_sql_escaped() -> None:
    assert _quoted_identifier("nora_app") == '"nora_app"'
    assert _quoted_literal("private'value") == "'private''value'"


@pytest.mark.parametrize("value", ["Nora", "nora-app", "x; DROP ROLE nora", ""])
def test_postgres_role_identifier_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="lowercase PostgreSQL identifier"):
        _quoted_identifier(value)


@pytest.mark.asyncio
async def test_existing_postgres_role_has_privileged_attributes_revoked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admin_url = tmp_path / "admin-url"
    app_password = tmp_path / "app-password"
    admin_url.write_text("postgresql://nora_admin:secret@db/nora", encoding="utf-8")
    app_password.write_text("application-secret", encoding="utf-8")
    connection = _ExistingRoleConnection()

    async def connect(_url: str) -> _ExistingRoleConnection:
        return connection

    monkeypatch.setattr(init_postgres_role.asyncpg, "connect", connect)
    monkeypatch.setenv("DATABASE_ADMIN_URL_FILE", str(admin_url))
    monkeypatch.setenv("POSTGRES_APP_USER", "nora_app")
    monkeypatch.setenv("POSTGRES_APP_PASSWORD_FILE", str(app_password))

    await init_postgres_role.run()

    alter_role = next(item for item in connection.statements if item.startswith("ALTER ROLE"))
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in alter_role
