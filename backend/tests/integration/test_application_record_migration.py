"""ApplicationRecord migration round-trip and database constraints."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_application_record_migration_round_trip_and_constraints(database_url: str) -> None:
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "0019_company_assessment_identity")
    command.upgrade(configuration, "0020_application_records")

    async def verify() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_name, constraint_name "
                    "FROM information_schema.table_constraints "
                    "WHERE table_name IN "
                    "('application_records', 'application_record_transitions')"
                )
            )
            constraints = {(row[0], row[1]) for row in rows}
            assert (
                "application_records",
                "fk_application_record_apply_decision",
            ) in constraints
            assert (
                "application_records",
                "fk_application_record_variant_owner",
            ) in constraints
            assert (
                "application_records",
                "ck_application_record_pdf_reference",
            ) in constraints
            assert (
                "application_records",
                "ck_application_record_draft_reference",
            ) in constraints
            assert (
                "application_record_transitions",
                "uq_application_transition_record_version",
            ) in constraints
            assert (
                "application_record_transitions",
                "ck_application_transition_applied_channel",
            ) in constraints
        await engine.dispose()

    asyncio.run(verify())
    command.downgrade(configuration, "0019_company_assessment_identity")
    command.upgrade(configuration, "0020_application_records")
