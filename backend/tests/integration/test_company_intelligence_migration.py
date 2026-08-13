"""Company intelligence migration upgrade and downgrade tests."""

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


def test_company_intelligence_migration_fixes_all_versioned_owner_relationships() -> None:
    migration = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0015_company_intelligence.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "uq_company_snapshot_identity",
        "fk_company_snapshot_source_owner",
        "uq_company_assessment_report",
        "uq_company_assessment_generation",
        "fk_company_assessment_report_owner",
        "fk_company_assessment_case_owner",
        "fk_company_assessment_snapshot_owner",
        "ck_company_snapshot_value_statuses",
        "ck_company_snapshot_anonymous_facts",
        "ck_company_snapshot_stale_facts",
        "ck_company_assessment_case_compat_version",
        "ck_company_assessment_status",
    ):
        assert marker in migration


def test_company_intelligence_migration_round_trip(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def inspect_upgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables, snapshot_unique, snapshot_foreign, snapshot_checks = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "company_snapshots"
                        )
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_foreign_keys("company_snapshots")
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_check_constraints(
                            "company_snapshots"
                        )
                    },
                )
            )
            assessment_unique, assessment_foreign, assessment_checks = await connection.run_sync(
                lambda sync_connection: (
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "company_assessments"
                        )
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_foreign_keys("company_assessments")
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_check_constraints(
                            "company_assessments"
                        )
                    },
                )
            )
        await engine.dispose()
        assert tables >= {"company_snapshots", "company_assessments"}
        assert "uq_company_snapshot_identity" in snapshot_unique
        assert "fk_company_snapshot_source_owner" in snapshot_foreign
        assert snapshot_checks >= {
            "ck_company_snapshot_value_statuses",
            "ck_company_snapshot_anonymous_facts",
            "ck_company_snapshot_stale_facts",
        }
        assert assessment_unique >= {
            "uq_company_assessment_report",
            "uq_company_assessment_generation",
        }
        assert assessment_foreign >= {
            "fk_company_assessment_report_owner",
            "fk_company_assessment_case_owner",
            "fk_company_assessment_snapshot_owner",
        }
        assert "ck_company_assessment_case_compat_version" in assessment_checks
        assert "ck_company_assessment_status" in assessment_checks

    async def inspect_downgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
        await engine.dispose()
        assert "company_snapshots" not in tables
        assert "company_assessments" not in tables

    try:
        command.upgrade(configuration, "0014_artifacts_sources")
        command.upgrade(configuration, "0015_company_intelligence")
        asyncio.run(inspect_upgrade())
        command.downgrade(configuration, "0014_artifacts_sources")
        asyncio.run(inspect_downgrade())
        command.upgrade(configuration, "0015_company_intelligence")
        asyncio.run(inspect_upgrade())
    finally:
        _reset_schema(database_url)
