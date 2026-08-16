"""InterviewCase migration round-trip and database constraints."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _reset_schema(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


def test_interview_case_migration_round_trip_and_constraints(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def schema_contract() -> tuple[set[str], set[str], set[str]]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            constraints = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'interview_cases'"
                )
            )
            indexes = await connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'interview_cases'")
            )
            result = (
                {row[0] for row in tables},
                {row[0] for row in constraints},
                {row[0] for row in indexes},
            )
        await engine.dispose()
        return result

    try:
        command.upgrade(configuration, "0021_beta_auth_security")
        command.upgrade(configuration, "0022_interview_cases")
        tables, constraints, indexes = asyncio.run(schema_contract())
        assert "interview_cases" in tables
        assert constraints >= {
            "fk_interview_case_application_owner",
            "ck_interview_case_mode_fields",
            "ck_interview_case_identity",
            "uq_interview_case_version",
            "uq_interview_case_owner_key",
        }
        assert indexes >= {
            "ix_interview_cases_id",
            "ix_interview_cases_owner_id",
            "ix_interview_cases_owner_start",
        }

        command.downgrade(configuration, "0021_beta_auth_security")
        assert "interview_cases" not in asyncio.run(schema_contract())[0]
        command.upgrade(configuration, "0022_interview_cases")
        assert "interview_cases" in asyncio.run(schema_contract())[0]
    finally:
        _reset_schema(database_url)
