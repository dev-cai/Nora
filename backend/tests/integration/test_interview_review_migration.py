"""Interview review and memory candidate migration contract."""

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


def test_interview_review_migration_creates_confirmation_contract(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def schema() -> tuple[set[str], set[str]]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            constraints = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name IN ('interview_reviews', 'memory_candidates')"
                )
            )
            value = ({row[0] for row in tables}, {row[0] for row in constraints})
        await engine.dispose()
        return value

    try:
        command.upgrade(configuration, "0026_interview_reviews_memory")
        tables, constraints = asyncio.run(schema())
        assert {"interview_reviews", "memory_candidates"} <= tables
        assert {
            "fk_interview_review_case_owner",
            "ck_memory_candidate_kind",
            "ck_memory_candidate_status",
            "ck_memory_candidate_confidence",
        } <= constraints
        command.downgrade(configuration, "0025_interview_preparations")
        assert "memory_candidates" not in asyncio.run(schema())[0]
    finally:
        _reset_schema(database_url)
