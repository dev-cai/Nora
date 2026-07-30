"""Identity API 集成测试。"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from nora.apps.api import create_app
from nora.domain.base.exceptions import NoraError
from nora.domain.identity import User
from nora.infrastructure.config import Settings
from nora.infrastructure.database import (
    Base,
    SqlAlchemyUserRepository,
    UserRecord,
    create_session_factory,
)


def reset_database(database_url: str) -> None:
    """重建隔离的 PostgreSQL 测试表。"""

    async def reset_tables() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset_tables())


def test_register_login_and_current_user(database_url: str) -> None:
    reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    with TestClient(create_app(settings)) as client:
        registered = client.post(
            "/auth/register",
            json={"username": "Alice", "email": "Alice@example.com", "password": "password-123"},
        )
        assert registered.status_code == 201
        assert registered.json()["username"] == "alice"
        assert registered.json()["email"] == "alice@example.com"
        assert "password" not in registered.text

        duplicate = client.post(
            "/auth/register",
            json={"username": "alice", "email": "other@example.com", "password": "password-123"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error_code"] == "username_conflict"

        duplicate_email = client.post(
            "/auth/register",
            json={"username": "other", "email": "ALICE@example.com", "password": "password-123"},
        )
        assert duplicate_email.status_code == 409
        assert duplicate_email.json()["error_code"] == "email_conflict"

        invalid_login = client.post(
            "/auth/login", json={"username": "alice", "password": "wrong-password"}
        )
        assert invalid_login.status_code == 401
        assert invalid_login.headers["WWW-Authenticate"] == "Bearer"

        login = client.post("/auth/login", json={"username": "ALICE", "password": "password-123"})
        assert login.status_code == 200
        token = login.json()["access_token"]

        missing_token = client.get("/auth/me")
        assert missing_token.status_code == 401

        current_user = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert current_user.status_code == 200
        assert current_user.json()["username"] == "alice"

        invalid_token = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})
        assert invalid_token.status_code == 401

    assert UserRecord.__tablename__ == "users"


def test_identity_endpoint_reports_missing_database_as_unavailable() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "password-123"},
        )

    assert response.status_code == 503
    assert response.json()["error_code"] == "database_unavailable"


@pytest.mark.asyncio
async def test_database_identity_conflicts_are_stable_and_rollback(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)
    async with factory() as session:
        repository = SqlAlchemyUserRepository(session)
        original = User.create("alice", "alice@example.com")
        await repository.add(original, "hash")
        await repository.commit()

        with pytest.raises(NoraError) as username_error:
            await repository.add(User.create("alice", "other@example.com"), "hash")
        assert username_error.value.error_code == "username_conflict"

        with pytest.raises(NoraError) as email_error:
            await repository.add(User.create("other", "alice@example.com"), "hash")
        assert email_error.value.error_code == "email_conflict"

        recovered = User.create("recovered", "recovered@example.com")
        await repository.add(recovered, "hash")
        await repository.commit()
        assert await repository.get_by_id(recovered.id) == recovered
