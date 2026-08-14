"""Resume PDF migration round-trip and exact-reference constraints."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.infrastructure.database import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_resume_pdf_migration_round_trip_and_constraints(database_url: str) -> None:
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await engine.dispose()

    asyncio.run(reset())
    command.upgrade(configuration, "0016_resume_variants")
    command.upgrade(configuration, "0017_resume_pdfs")

    async def constraint_names() -> set[str]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_name = 'resume_pdfs'"
                )
            )
            result = {row[0] for row in rows}
        await engine.dispose()
        return result

    names = asyncio.run(constraint_names())

    assert "fk_resume_pdf_variant_owner" in names
    assert "fk_resume_pdf_template" in names
    assert "fk_resume_pdf_artifact_owner" in names
    assert "uq_resume_pdf_owner_generation" in names
    assert "ck_resume_pdf_artifact_state" in names

    command.downgrade(configuration, "0016_resume_variants")
    command.upgrade(configuration, "0017_resume_pdfs")
