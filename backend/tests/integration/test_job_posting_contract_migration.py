"""岗位公开契约迁移的回填、约束和降级测试。"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.opportunity import CreateJobPostingCommand, CreateJobPostingUseCase
from app.domain.base.exceptions import ApplicationError
from app.infrastructure.database import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyJobPostingRepository,
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _reset_schema(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


def test_job_posting_public_contract_migrates_legacy_metadata(database_url: str) -> None:
    _reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    owner_id = uuid4()
    posting_id = uuid4()
    idempotency_id = uuid4()
    now = datetime.now(timezone.utc)
    legacy_fingerprint = hashlib.sha256(
        json.dumps(
            {"jd_text": "Legacy JD", "source_type": "manual", "source_url": None},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    async def insert_legacy_row() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, created_at, updated_at, version, username, email,
                        password_hash, is_active
                    ) VALUES (
                        :id, :now, :now, 1, 'legacy-job-owner',
                        'legacy-job-owner@example.com', 'unused-test-hash', true
                    )
                    """
                ),
                {"id": owner_id, "now": now},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO job_postings (
                        id, created_at, updated_at, version, owner_id, jd_text,
                        job_title, company_name, location, source_type, source_url,
                        imported_at, text_summary, status
                    ) VALUES (
                        :id, :now, :now, 1, :owner_id, 'Legacy JD',
                        NULL, NULL, NULL, 'manual', NULL, :now, 'Legacy JD', 'active'
                    )
                    """
                ),
                {"id": posting_id, "owner_id": owner_id, "now": now},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO job_posting_idempotency (
                        id, created_at, updated_at, version, owner_id,
                        idempotency_key, request_fingerprint, job_posting_id
                    ) VALUES (
                        :id, :now, :now, 1, :owner_id,
                        'legacy-key', :fingerprint, :posting_id
                    )
                    """
                ),
                {
                    "id": idempotency_id,
                    "owner_id": owner_id,
                    "posting_id": posting_id,
                    "fingerprint": legacy_fingerprint,
                    "now": now,
                },
            )
        await engine.dispose()

    async def verify_legacy_replay() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            repository = SqlAlchemyJobPostingRepository(session, owner_id)
            use_case = CreateJobPostingUseCase(repository, SqlAlchemyAuditEventRepository(session))
            replayed = await use_case.execute(
                CreateJobPostingCommand(
                    owner_id=owner_id,
                    idempotency_key="legacy-key",
                    jd_text="Legacy JD",
                )
            )
            assert replayed.replayed is True
            assert replayed.job_posting.id == posting_id

            with pytest.raises(ApplicationError) as error:
                await use_case.execute(
                    CreateJobPostingCommand(
                        owner_id=owner_id,
                        idempotency_key="legacy-key",
                        jd_text="Changed JD",
                    )
                )
            assert error.value.error_code == "idempotency_conflict"
        await engine.dispose()

    async def verify_upgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            values = await connection.execute(
                text(
                    """
                    SELECT job_title, company_name, location
                    FROM job_postings WHERE id = :id
                    """
                ),
                {"id": posting_id},
            )
            assert values.one() == ("未提供职位", "未提供公司", "未提供地点")
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]: column["nullable"]
                    for column in inspect(sync_connection).get_columns("job_postings")
                    if column["name"] in {"job_title", "company_name", "location"}
                }
            )
        assert columns == {"job_title": False, "company_name": False, "location": False}

        with pytest.raises(DBAPIError, match="job_title_nonempty"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO job_postings (
                            id, owner_id, jd_text, job_title, company_name, location,
                            source_type, imported_at, text_summary, status
                        ) VALUES (
                            :id, :owner_id, 'Invalid', ' ', 'Example', 'Shanghai',
                            'manual', :now, 'Invalid', 'active'
                        )
                        """
                    ),
                    {"id": uuid4(), "owner_id": owner_id, "now": now},
                )
        await engine.dispose()

    async def verify_downgrade() -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]: column["nullable"]
                    for column in inspect(sync_connection).get_columns("job_postings")
                    if column["name"] in {"job_title", "company_name", "location"}
                }
            )
        await engine.dispose()
        assert columns == {"job_title": True, "company_name": True, "location": True}

    try:
        command.upgrade(configuration, "0006_audit_event_target_version")
        asyncio.run(insert_legacy_row())
        command.upgrade(configuration, "head")
        asyncio.run(verify_legacy_replay())
        asyncio.run(verify_upgrade())
        command.downgrade(configuration, "0006_audit_event_target_version")
        asyncio.run(verify_downgrade())
    finally:
        _reset_schema(database_url)
