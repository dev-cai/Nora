"""DecisionReport migration upgrade and downgrade tests."""

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


def _reset_schema(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


def test_decision_report_migration_adds_and_removes_versioned_storage(
    database_url: str,
) -> None:
    _reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def inspect_upgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables, unique_constraints, foreign_keys = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "decision_reports"
                        )
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_foreign_keys("decision_reports")
                    },
                )
            )
        await engine.dispose()
        assert "decision_reports" in tables
        assert unique_constraints >= {
            "uq_decision_report_case_version",
            "uq_decision_report_generation",
        }
        assert "fk_decision_report_case_owner" in foreign_keys

    async def inspect_downgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables, case_constraints = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "decision_cases"
                        )
                    },
                )
            )
        await engine.dispose()
        assert "decision_reports" not in tables
        assert "uq_decision_case_id_owner" not in case_constraints

    try:
        command.upgrade(configuration, "0011_decision_cases")
        command.upgrade(configuration, "0012_decision_reports")
        asyncio.run(inspect_upgrade())
        command.downgrade(configuration, "0011_decision_cases")
        asyncio.run(inspect_downgrade())
    finally:
        _reset_schema(database_url)
