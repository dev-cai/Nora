"""审计事件迁移的 PostgreSQL append-only 约束测试。"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
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


def test_audit_event_migration_rejects_update_and_delete(database_url: str) -> None:
    reset_schema(database_url)
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(configuration, "head")

    async def verify() -> None:
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

        await engine.dispose()

    try:
        asyncio.run(verify())
    finally:
        reset_schema(database_url)
