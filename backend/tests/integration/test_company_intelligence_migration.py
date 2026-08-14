"""Company intelligence migration upgrade and downgrade tests."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine


def _reset_schema(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


def _assessment_identity(values: dict[str, object], *, include_case_version: bool) -> str:
    identity_values = {
        "company_snapshot_id": str(values["company_snapshot_id"]),
        "company_snapshot_version": 1,
        "decision_case_id": str(values["decision_case_id"]),
        "generator_version": "m4-company-assessment-v1",
        "report_id": str(values["report_id"]),
        "report_version": 1,
    }
    if include_case_version:
        identity_values["decision_case_version"] = 1
    return hashlib.sha256(
        json.dumps(
            identity_values,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _seed_assessment_graph(database_url: str) -> dict[str, object]:
    values: dict[str, object] = {
        name: uuid4()
        for name in (
            "owner_id",
            "posting_id",
            "requirement_record_id",
            "requirement_id",
            "profile_record_id",
            "profile_id",
            "resume_id",
            "decision_case_id",
            "report_id",
            "artifact_id",
            "source_id",
            "snapshot_record_id",
            "company_snapshot_id",
            "assessment_id",
        )
    }
    values["now"] = datetime(2026, 8, 15, tzinfo=timezone.utc)
    values["old_identity"] = _assessment_identity(values, include_case_version=True)
    values["new_identity"] = _assessment_identity(values, include_case_version=False)

    async def seed() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, created_at, updated_at, version, username, email,
                        password_hash, is_active
                    ) VALUES (
                        :owner_id, :now, :now, 1, 'identity-migration-owner',
                        'identity-migration-owner@example.com', 'unused-test-hash', true
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO job_postings (
                        id, created_at, updated_at, version, owner_id, jd_text,
                        job_title, company_name, location, source_type, source_url,
                        imported_at, text_summary, status
                    ) VALUES (
                        :posting_id, :now, :now, 1, :owner_id, 'Build APIs',
                        'Engineer', 'Example Inc', 'Remote', 'manual', NULL,
                        :now, 'Build APIs', 'active'
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO job_requirement_snapshots (
                        record_id, snapshot_id, owner_id, version, job_posting_id,
                        job_posting_version, content, snapshot_created_at, updated_at
                    ) VALUES (
                        :requirement_record_id, :requirement_id, :owner_id, 1,
                        :posting_id, 1, '{"required_skills": []}'::jsonb, :now, :now
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO candidate_profile_versions (
                        record_id, profile_id, owner_id, version, content,
                        profile_created_at, updated_at
                    ) VALUES (
                        :profile_record_id, :profile_id, :owner_id, 1,
                        '{"basic_information": {}}'::jsonb, :now, :now
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO resume_versions (
                        id, owner_id, version, candidate_profile_id, profile_version,
                        title, content, published_at
                    ) VALUES (
                        :resume_id, :owner_id, 1, :profile_id, 1,
                        'Migration resume', '{"snapshot": 1}'::jsonb, :now
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO decision_cases (
                        id, owner_id, job_posting_id, job_posting_version,
                        job_requirement_snapshot_id, job_requirement_snapshot_version,
                        candidate_profile_id, candidate_profile_version,
                        resume_version_id, resume_version, rule_set_version,
                        input_fingerprint, status, created_at, completed_at,
                        failure_code, failure_message
                    ) VALUES (
                        :decision_case_id, :owner_id, :posting_id, 1,
                        :requirement_id, 1, :profile_id, 1, :resume_id, 1,
                        'm3-rules-v1', :input_fingerprint, 'completed', :now, :now,
                        NULL, NULL
                    )
                    """
                ),
                {**values, "input_fingerprint": "a" * 64},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO decision_reports (
                        id, owner_id, decision_case_id, version, rule_set_version,
                        generator_version, content, generated_at
                    ) VALUES (
                        :report_id, :owner_id, :decision_case_id, 1, 'm3-rules-v1',
                        'm3-report-v1', '{"recommendation": "apply"}'::jsonb, :now
                    )
                    """
                ),
                values,
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO artifacts (
                        id, owner_id, version, kind, content_type, size_bytes, sha256,
                        object_key, status, idempotency_key, generator_version,
                        generation_identity, created_at, deleted_at
                    ) VALUES (
                        :artifact_id, :owner_id, 1, 'source', 'text/plain', 1,
                        :content_sha256, 'migration/source.txt', 'available',
                        'migration-source', NULL, NULL, :now, NULL
                    )
                    """
                ),
                {**values, "content_sha256": "b" * 64},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO source_documents (
                        id, owner_id, version, artifact_id, artifact_version,
                        source_kind, acquisition_method, license_note, locator,
                        acquired_at, published_at, content_sha256, created_at
                    ) VALUES (
                        :source_id, :owner_id, 1, :artifact_id, 1, 'manual',
                        'user_entry', 'user supplied', NULL, :now, :now,
                        :content_sha256, :now
                    )
                    """
                ),
                {**values, "content_sha256": "b" * 64},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO company_snapshots (
                        record_id, snapshot_id, owner_id, version, company_name,
                        size, size_status, industry, industry_status, review_summary,
                        review_status, source_id, source_version, source_tier,
                        source_kind, acquisition_method, license_note, acquired_at,
                        published_at, source_content_sha256, freshness, content_sha256,
                        snapshot_created_at
                    ) VALUES (
                        :snapshot_record_id, :company_snapshot_id, :owner_id, 1,
                        'Example Inc', '100-499', 'confirmed', 'Software', 'confirmed',
                        NULL, 'unknown', :source_id, 1, 'official/company', 'manual',
                        'user_entry', 'user supplied', :now, :now, :source_sha256,
                        'fresh', :snapshot_sha256, :now
                    )
                    """
                ),
                {**values, "source_sha256": "b" * 64, "snapshot_sha256": "c" * 64},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO company_assessments (
                        id, owner_id, version, report_id, report_version,
                        decision_case_id, decision_case_version, company_snapshot_id,
                        company_snapshot_version, status, status_reason,
                        generator_version, generation_identity, assessment_created_at
                    ) VALUES (
                        :assessment_id, :owner_id, 1, :report_id, 1,
                        :decision_case_id, 1, :company_snapshot_id, 1, 'available',
                        'fixed_snapshot', 'm4-company-assessment-v1', :old_identity, :now
                    )
                    """
                ),
                values,
            )
        await engine.dispose()

    asyncio.run(seed())
    return values


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


def test_company_assessment_identity_migration_preserves_graph_and_is_reversible(
    database_url: str,
) -> None:
    _reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    async def state() -> dict[str, object]:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            columns, checks, foreign_keys, unique_constraints = await connection.run_sync(
                lambda sync_connection: (
                    {
                        item["name"]: item
                        for item in inspect(sync_connection).get_columns("company_assessments")
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_check_constraints(
                            "company_assessments"
                        )
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_foreign_keys("company_assessments")
                    },
                    {
                        item["name"]
                        for item in inspect(sync_connection).get_unique_constraints(
                            "company_assessments"
                        )
                    },
                )
            )
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, owner_id, report_id, decision_case_id,
                               company_snapshot_id, generation_identity
                        FROM company_assessments
                        """
                    )
                )
            ).one()
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        await engine.dispose()
        return {
            "columns": columns,
            "checks": checks,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "row": row,
            "revision": revision,
        }

    async def install_failure_trigger() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                """
                CREATE FUNCTION reject_company_assessment_identity_rewrite()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'forced identity rewrite failure';
                END;
                $$
                """
            )
            await connection.exec_driver_sql(
                """
                CREATE TRIGGER reject_company_assessment_identity_rewrite
                BEFORE UPDATE OF generation_identity ON company_assessments
                FOR EACH ROW EXECUTE FUNCTION reject_company_assessment_identity_rewrite()
                """
            )
        await engine.dispose()

    async def remove_failure_trigger() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "DROP TRIGGER reject_company_assessment_identity_rewrite ON company_assessments"
            )
            await connection.exec_driver_sql(
                "DROP FUNCTION reject_company_assessment_identity_rewrite()"
            )
        await engine.dispose()

    try:
        command.upgrade(configuration, "0018_message_drafts")
        values = _seed_assessment_graph(database_url)
        asyncio.run(install_failure_trigger())
        with pytest.raises(DBAPIError, match="forced identity rewrite failure"):
            command.upgrade(configuration, "0019_company_assessment_identity")

        failed = asyncio.run(state())
        assert failed["revision"] == "0018_message_drafts"
        assert "decision_case_version" in failed["columns"]
        assert failed["row"].generation_identity == values["old_identity"]
        asyncio.run(remove_failure_trigger())

        command.upgrade(configuration, "0019_company_assessment_identity")
        upgraded = asyncio.run(state())
        assert upgraded["revision"] == "0019_company_assessment_identity"
        assert "decision_case_version" not in upgraded["columns"]
        assert (
            not {
                "ck_company_assessment_case_version",
                "ck_company_assessment_case_compat_version",
            }
            & upgraded["checks"]
        )
        assert upgraded["foreign_keys"] >= {
            "fk_company_assessment_report_owner",
            "fk_company_assessment_case_owner",
            "fk_company_assessment_snapshot_owner",
        }
        assert upgraded["unique_constraints"] >= {
            "uq_company_assessment_report",
            "uq_company_assessment_generation",
        }
        row = upgraded["row"]
        assert row.id == values["assessment_id"]
        assert row.owner_id == values["owner_id"]
        assert row.report_id == values["report_id"]
        assert row.decision_case_id == values["decision_case_id"]
        assert row.company_snapshot_id == values["company_snapshot_id"]
        assert row.generation_identity == values["new_identity"]

        command.downgrade(configuration, "0018_message_drafts")
        downgraded = asyncio.run(state())
        assert downgraded["revision"] == "0018_message_drafts"
        restored_column = downgraded["columns"]["decision_case_version"]
        assert restored_column["nullable"] is False
        assert restored_column["default"] is None
        assert downgraded["checks"] >= {
            "ck_company_assessment_case_version",
            "ck_company_assessment_case_compat_version",
        }
        assert downgraded["row"].generation_identity == values["old_identity"]

        command.upgrade(configuration, "0019_company_assessment_identity")
        reupgraded = asyncio.run(state())
        assert "decision_case_version" not in reupgraded["columns"]
        assert reupgraded["row"].generation_identity == values["new_identity"]
    finally:
        _reset_schema(database_url)
