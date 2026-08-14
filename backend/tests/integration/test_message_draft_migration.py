"""MessageDraft migration round-trip and append-only constraints."""

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


def test_message_draft_migration_round_trip_and_constraints(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def schema_names() -> tuple[set[str], set[str], set[str]]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            foreign_keys = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'message_drafts' AND constraint_type = 'FOREIGN KEY'"
                )
            )
            constraints = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'message_drafts'"
                )
            )
            result = (
                {row[0] for row in tables},
                {row[0] for row in foreign_keys},
                {row[0] for row in constraints},
            )
        await engine.dispose()
        return result

    async def index_names() -> set[str]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            indexes = await connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'message_drafts'")
            )
            result = {row[0] for row in indexes}
        await engine.dispose()
        return result

    async def constraint_definition(name: str) -> str:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"),
                {"name": name},
            )
        await engine.dispose()
        assert isinstance(definition, str)
        return definition

    try:
        command.upgrade(configuration, "0017_resume_pdfs")
        command.upgrade(configuration, "0018_message_drafts")
        tables, foreign_keys, constraints = asyncio.run(schema_names())
        assert "message_drafts" in tables
        assert foreign_keys >= {
            "fk_message_draft_variant_owner",
            "fk_message_draft_profile_owner",
            "fk_message_draft_resume_owner",
            "fk_message_draft_job_owner",
            "fk_message_draft_company_owner",
            "fk_message_draft_previous_version",
        }
        assert "ck_message_draft_revision_chain" in constraints
        assert "company_industry IS NULL" in asyncio.run(
            constraint_definition("ck_message_draft_company_identity")
        )
        assert "uq_message_draft_owner_generation" in asyncio.run(index_names())

        command.downgrade(configuration, "0017_resume_pdfs")
        assert "message_drafts" not in asyncio.run(schema_names())[0]
        command.upgrade(configuration, "0018_message_drafts")
        assert "message_drafts" in asyncio.run(schema_names())[0]
    finally:
        _reset_schema(database_url)
