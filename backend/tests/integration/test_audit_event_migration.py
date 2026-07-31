"""审计事件迁移的 PostgreSQL append-only 约束测试。"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine


def reset_schema(database_url: str) -> None:
    """重建隔离测试数据库的 public schema。"""

    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


def test_audit_event_target_version_migrates_existing_rows_and_remains_append_only(
    database_url: str,
) -> None:
    reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(configuration, "0005_audit_events")

    async def insert_legacy_event() -> tuple[UUID, UUID]:
        engine = create_async_engine(database_url)
        actor_id = uuid4()
        event_id = uuid4()
        target_id = uuid4()
        now = datetime.now(timezone.utc)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, created_at, updated_at, version, username, email,
                        password_hash, is_active
                    ) VALUES (
                        :id, :now, :now, 1, 'audit-user', 'audit@example.com',
                        'unused-test-hash', true
                    )
                    """
                ),
                {"id": actor_id, "now": now},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, actor_id, action, target_type, target_id,
                        before_summary, after_summary, occurred_at, idempotency_key
                    ) VALUES (
                        :id, :actor_id, 'create', 'job_posting', :target_id,
                        NULL, '{"status":"active"}', :now, 'job-1'
                    )
                    """
                ),
                {"id": event_id, "actor_id": actor_id, "target_id": target_id, "now": now},
            )
        await engine.dispose()
        return actor_id, event_id

    async def verify(actor_id: UUID, event_id: UUID) -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            target_version = await connection.scalar(
                text("SELECT target_version FROM audit_events WHERE id = :id"),
                {"id": event_id},
            )
        assert target_version == 1

        compatible_event_id = uuid4()
        with pytest.raises(DBAPIError, match="ck_audit_events_target_version"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO audit_events (
                            id, actor_id, action, target_type, target_id, target_version,
                            before_summary, after_summary, occurred_at, idempotency_key
                        ) VALUES (
                            :id, :actor_id, 'create', 'job_posting', :target_id, 0,
                            NULL, '{"status":"active"}', now(), 'invalid-version'
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "actor_id": actor_id,
                        "target_id": uuid4(),
                    },
                )

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, actor_id, action, target_type, target_id,
                        before_summary, after_summary, occurred_at, idempotency_key
                    ) VALUES (
                        :id, :actor_id, 'create', 'job_posting', :target_id,
                        NULL, '{"status":"active"}', now(), 'compatible-default'
                    )
                    """
                ),
                {
                    "id": compatible_event_id,
                    "actor_id": actor_id,
                    "target_id": uuid4(),
                },
            )
        async with engine.connect() as connection:
            compatible_version = await connection.scalar(
                text("SELECT target_version FROM audit_events WHERE id = :id"),
                {"id": compatible_event_id},
            )
        assert compatible_version == 1

        with pytest.raises(DBAPIError, match="audit_events are append-only"):
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE audit_events SET action = 'read' WHERE id = :id"),
                    {"id": event_id},
                )

        with pytest.raises(DBAPIError, match="audit_events are append-only"):
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM audit_events WHERE id = :id"),
                    {"id": event_id},
                )

        with pytest.raises(DBAPIError, match="audit_events are append-only"):
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE TABLE audit_events"))

        await engine.dispose()

    async def verify_downgrade_preserves_rows(event_id: UUID) -> None:
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("audit_events")
                }
            )
            stored_id = await connection.scalar(
                text("SELECT id FROM audit_events WHERE id = :id"),
                {"id": event_id},
            )
        await engine.dispose()
        assert "target_version" not in columns
        assert stored_id == event_id

    try:
        actor_id, event_id = asyncio.run(insert_legacy_event())
        command.upgrade(configuration, "head")
        asyncio.run(verify(actor_id, event_id))
        command.downgrade(configuration, "0005_audit_events")
        asyncio.run(verify_downgrade_preserves_rows(event_id))
    finally:
        reset_schema(database_url)
