"""Identity API 集成测试。"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.application.identity import IdentityManagementService, ManagementResult
from app.apps.api import create_app
from app.domain.base.exceptions import NoraError
from app.domain.identity import User
from app.infrastructure.auth import Argon2PasswordHasher
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    Base,
    BetaOwnerRecord,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyAuthenticationRateLimitRepository,
    SqlAlchemyIdentityManagementRepository,
    SqlAlchemyUserRepository,
    UserRecord,
    create_session_factory,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


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


def _production_settings(database_url: str, tmp_path: Path) -> Settings:
    key_ring = tmp_path / "keys"
    key_ring.mkdir()
    (key_ring / "active").write_text("production-test-jwt-key-value-32!", encoding="utf-8")
    return Settings(
        env="prod",
        database_url=database_url,
        auth_secret_key="production-legacy-secret-value-32!",
        auth_key_ring_directory=key_ring,
        auth_active_kid="active",
        auth_rate_limit_secret="production-rate-limit-secret-32!",
        public_origin="https://nora.example",
        trusted_proxy_cidr="10.0.0.0/8",
    )


def test_production_rejects_origin_and_hides_registration_before_body_parsing(
    database_url: str, tmp_path: Path
) -> None:
    reset_database(database_url)
    settings = _production_settings(database_url, tmp_path)
    with TestClient(create_app(settings)) as client:
        denied = client.post(
            "/auth/login",
            headers={"Origin": "https://attacker.example"},
            content=b"not-json",
        )
        assert denied.status_code == 403
        assert denied.json()["error_code"] == "origin_not_allowed"
        assert "access-control-allow-origin" not in denied.headers

        hidden = client.post(
            "/auth/register",
            headers={"Origin": "https://nora.example", "Content-Type": "application/json"},
            content=b"not-json",
        )
        assert hidden.status_code == 404
        assert hidden.json()["error_code"] == "entity_not_found"


def test_production_preflight_allows_published_contract_and_rejects_unknown_method(
    database_url: str, tmp_path: Path
) -> None:
    reset_database(database_url)
    settings = _production_settings(database_url, tmp_path)
    with TestClient(create_app(settings)) as client:
        actual = client.post(
            "/auth/login",
            headers={"Origin": "https://nora.example"},
            json={"username": "unknown", "password": "wrong"},
        )
        assert actual.status_code == 401
        assert actual.headers["access-control-allow-origin"] == "https://nora.example"

        allowed = client.options(
            "/auth/login",
            headers={
                "Origin": "https://nora.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://nora.example"

        rejected = client.options(
            "/auth/login",
            headers={
                "Origin": "https://nora.example",
                "Access-Control-Request-Method": "PATCH",
            },
        )
        assert rejected.status_code == 403
        assert rejected.json()["error_code"] == "origin_not_allowed"
        assert "access-control-allow-origin" not in rejected.headers


def test_untrusted_forwarded_headers_cannot_bypass_coarse_limit(
    database_url: str, tmp_path: Path
) -> None:
    reset_database(database_url)
    settings = _production_settings(database_url, tmp_path)
    with TestClient(create_app(settings)) as client:
        for attempt in range(30):
            response = client.post(
                "/auth/login",
                headers={
                    "X-Forwarded-For": f"198.51.100.{attempt + 1}",
                    "X-Forwarded-Proto": "https",
                    "Content-Type": "application/json",
                },
                content=b"not-json",
            )
            assert response.status_code == 422

        limited = client.post(
            "/auth/login",
            headers={
                "X-Forwarded-For": "203.0.113.200",
                "X-Forwarded-Proto": "https",
                "Content-Type": "application/json",
            },
            content=b"not-json",
        )
        assert limited.status_code == 429
        assert limited.json()["error_code"] == "authentication_rate_limited"
        assert int(limited.headers["Retry-After"]) >= 1


def test_login_target_rate_limit_and_recovery_invalidate_old_session(
    database_url: str,
) -> None:
    reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    async def bootstrap() -> None:
        engine = create_async_engine(database_url)
        factory = create_session_factory(engine)
        async with factory() as session:
            result = await IdentityManagementService(
                SqlAlchemyIdentityManagementRepository(
                    session, SqlAlchemyAuditEventRepository(session)
                ),
                Argon2PasswordHasher(),
            ).bootstrap_owner("bootstrap-1", "alice", "alice@example.com", "password-123")
            assert result.status == "created"
        await engine.dispose()

    async def recover() -> None:
        engine = create_async_engine(database_url)
        factory = create_session_factory(engine)
        async with factory() as session:
            result = await IdentityManagementService(
                SqlAlchemyIdentityManagementRepository(
                    session, SqlAlchemyAuditEventRepository(session)
                ),
                Argon2PasswordHasher(),
            ).recover_credentials("recover-1", "new-password-123")
            assert result.session_version == 2
        await engine.dispose()

    asyncio.run(bootstrap())
    with TestClient(create_app(settings)) as client:
        login = client.post("/auth/login", json={"username": "alice", "password": "password-123"})
        assert login.status_code == 200
        old_token = login.json()["access_token"]

        for _ in range(5):
            failed = client.post("/auth/login", json={"username": "unknown", "password": "wrong"})
            assert failed.status_code == 401
        limited = client.post("/auth/login", json={"username": "unknown", "password": "wrong"})
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1

        asyncio.run(recover())
        revoked = client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert revoked.status_code == 401
        renewed = client.post(
            "/auth/login", json={"username": "alice", "password": "new-password-123"}
        )
        assert renewed.status_code == 200


@pytest.mark.asyncio
async def test_login_rate_limit_recovers_after_fixed_window(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)
    now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    async with factory() as session:
        repository = SqlAlchemyAuthenticationRateLimitRepository(session)
        for _ in range(repository.LOGIN_TARGET_LIMIT):
            decision = await repository.reserve_login("a" * 64, "b" * 64, now)
            assert decision.allowed is True

        blocked = await repository.reserve_login("a" * 64, "b" * 64, now)
        assert blocked.allowed is False
        assert blocked.retry_after == 15 * 60 + 1

        recovered = await repository.reserve_login(
            "a" * 64,
            "b" * 64,
            now + timedelta(minutes=15, seconds=1),
        )
        assert recovered.allowed is True


@pytest.mark.asyncio
async def test_concurrent_bootstrap_provisions_exactly_one_owner(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)

    async def bootstrap(request_identity: str, username: str, email: str) -> ManagementResult:
        async with factory() as session:
            return await IdentityManagementService(
                SqlAlchemyIdentityManagementRepository(
                    session, SqlAlchemyAuditEventRepository(session)
                ),
                Argon2PasswordHasher(),
            ).bootstrap_owner(request_identity, username, email, "password-123")

    first, second = await asyncio.gather(
        bootstrap("bootstrap-a", "alice", "alice@example.com"),
        bootstrap("bootstrap-b", "bob", "bob@example.com"),
    )

    assert {first.status, second.status} == {"created", "already_provisioned"}
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(BetaOwnerRecord)) == 1


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
