"""岗位快照 API 的 PostgreSQL 集成测试。"""

import asyncio
from uuid import UUID, uuid4

from app.apps.api import create_app
from app.infrastructure.config import Settings
from app.infrastructure.database import AuditEventRecord, Base
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def reset_database(database_url: str) -> None:
    """重建隔离的 PostgreSQL 测试表。"""

    async def reset_tables() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset_tables())


def register_and_login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password-123",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "password-123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def load_audit_events(database_url: str) -> list[AuditEventRecord]:
    """从隔离数据库读取岗位 API 产生的审计记录。"""

    async def load() -> list[AuditEventRecord]:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            records = (await session.scalars(select(AuditEventRecord))).all()
        await engine.dispose()
        return list(records)

    return asyncio.run(load())


def test_job_posting_create_replay_conflict_and_user_scope(database_url: str) -> None:
    reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    with TestClient(create_app(settings)) as client:
        token_a = register_and_login(client, "alice")
        token_b = register_and_login(client, "bob")
        auth_a = {"Authorization": f"Bearer {token_a}"}
        auth_b = {"Authorization": f"Bearer {token_b}"}
        payload = {
            "jd_text": "  Senior Python Engineer\r\nBuild reliable APIs.  ",
            "source_type": "url",
            "source_url": "https://jobs.example.com/roles/123",
        }

        unauthenticated = client.post(
            "/job-postings",
            headers={"Idempotency-Key": "job-1"},
            json=payload,
        )
        assert unauthenticated.status_code == 401

        missing_key = client.post("/job-postings", headers=auth_a, json=payload)
        assert missing_key.status_code == 422

        created = client.post(
            "/job-postings",
            headers={**auth_a, "Idempotency-Key": "job-1"},
            json=payload,
        )
        assert created.status_code == 201
        assert created.json()["summary"] == "Senior Python Engineer Build reliable APIs."
        posting_id = created.json()["id"]

        replayed = client.post(
            "/job-postings",
            headers={**auth_a, "Idempotency-Key": "job-1"},
            json={**payload, "jd_text": "Senior Python Engineer\nBuild reliable APIs."},
        )
        assert replayed.status_code == 200
        assert replayed.json() == created.json()

        conflict = client.post(
            "/job-postings",
            headers={**auth_a, "Idempotency-Key": "job-1"},
            json={**payload, "jd_text": "A different role."},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "idempotency_conflict"

        fetched = client.get(f"/job-postings/{posting_id}", headers=auth_a)
        assert fetched.status_code == 200
        assert fetched.json() == created.json()

        hidden = client.get(f"/job-postings/{posting_id}", headers=auth_b)
        assert hidden.status_code == 404
        assert hidden.json()["error_code"] == "entity_not_found"

        missing = client.get(f"/job-postings/{uuid4()}", headers=auth_a)
        assert missing.status_code == 404

        other_owner_same_key = client.post(
            "/job-postings",
            headers={**auth_b, "Idempotency-Key": "job-1"},
            json={"jd_text": "Bob's role."},
        )
        assert other_owner_same_key.status_code == 201
        assert other_owner_same_key.json()["id"] != posting_id

        events = load_audit_events(database_url)
        assert len(events) == 2
        matching_events = [event for event in events if event.target_id == UUID(posting_id)]
        assert len(matching_events) == 1
        alice_event = matching_events[0]
        assert alice_event.action == "create"
        assert alice_event.target_type == "job_posting"
        assert alice_event.idempotency_key == "job-1"
        assert "Senior Python Engineer" in (alice_event.after_summary or "")
