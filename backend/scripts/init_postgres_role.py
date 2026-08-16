"""Provision the least-privilege PostgreSQL application role after migrations."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import asyncpg

ROLE_PATTERN = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def _quoted_identifier(value: str) -> str:
    if ROLE_PATTERN.fullmatch(value) is None:
        raise ValueError("POSTGRES_APP_USER must be a lowercase PostgreSQL identifier")
    return f'"{value}"'


def _quoted_literal(value: str) -> str:
    if not value or len(value.encode("utf-8")) > 16 * 1024 or "\x00" in value:
        raise ValueError("POSTGRES_APP_PASSWORD_FILE must contain 1-16384 bytes")
    return "'" + value.replace("'", "''") + "'"


async def run() -> None:
    admin_url = _secret("DATABASE_ADMIN_URL")
    if admin_url.startswith("postgresql+asyncpg://"):
        admin_url = "postgresql://" + admin_url.removeprefix("postgresql+asyncpg://")
    role = _quoted_identifier(os.environ["POSTGRES_APP_USER"])
    password = _quoted_literal(_secret("POSTGRES_APP_PASSWORD"))
    connection = await asyncpg.connect(admin_url)
    try:
        exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)",
            os.environ["POSTGRES_APP_USER"],
        )
        if exists:
            await connection.execute(
                f"ALTER ROLE {role} WITH LOGIN PASSWORD {password} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
        else:
            await connection.execute(
                f"CREATE ROLE {role} LOGIN PASSWORD {password} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
        database_name = await connection.fetchval("SELECT current_database()")
        database = '"' + str(database_name).replace('"', '""') + '"'
        await connection.execute(f"GRANT CONNECT ON DATABASE {database} TO {role}")
        await connection.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        await connection.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
        )
        await connection.execute(
            f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {role}"
        )
        await connection.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
        )
        await connection.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {role}"
        )
    finally:
        await connection.close()
    print("postgres_application_role=ready")


def _secret(name: str) -> str:
    path = Path(os.environ[f"{name}_FILE"])
    return path.read_text(encoding="utf-8").rstrip("\r\n")


if __name__ == "__main__":
    asyncio.run(run())
