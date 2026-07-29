"""PostgreSQL-only integration test fixtures."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from nora.infrastructure.config import Settings
from nora.infrastructure.database import Base, create_database_engine, create_session_factory


@pytest.fixture
def database_url() -> str:
    """Return an explicitly configured PostgreSQL integration database."""

    value = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        pytest.fail(
            "PostgreSQL integration tests require TEST_DATABASE_URL or DATABASE_URL; "
            "run them through the Compose test service"
        )
    if make_url(value).drivername != "postgresql+asyncpg":
        pytest.fail("Integration tests require a postgresql+asyncpg database URL")
    return value


@pytest_asyncio.fixture
async def database_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Create a clean schema in the isolated PostgreSQL test database."""

    engine = create_database_engine(Settings(database_url=database_url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def session(database_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield an isolated SQLAlchemy session."""

    factory = create_session_factory(database_engine)
    async with factory() as value:
        yield value
