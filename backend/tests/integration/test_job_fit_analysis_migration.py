"""JobFitAnalysis migration round-trip and relational constraints."""

import asyncio
from pathlib import Path

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


def test_job_fit_analysis_migration_round_trip(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def schema_contract() -> tuple[set[str], set[str], set[str]]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables, unique_constraints, foreign_keys = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "job_fit_analyses"
                        )
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_foreign_keys("job_fit_analyses")
                    },
                )
            )
        await engine.dispose()
        return tables, unique_constraints, foreign_keys

    try:
        command.upgrade(configuration, "0022_interview_cases")
        command.upgrade(configuration, "0023_job_fit_analyses")
        tables, constraints, foreign_keys = asyncio.run(schema_contract())
        assert "job_fit_analyses" in tables
        assert constraints >= {
            "uq_job_fit_analysis_report_version",
            "uq_job_fit_analysis_generation",
        }
        assert foreign_keys >= {"fk_job_fit_analysis_report_owner"}

        command.downgrade(configuration, "0022_interview_cases")
        engine = create_async_engine(database_url)

        async def table_names() -> set[str]:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: set(inspect(sync_connection).get_table_names())
                )

        assert "job_fit_analyses" not in asyncio.run(table_names())
        asyncio.run(engine.dispose())
    finally:
        _reset_schema(database_url)
