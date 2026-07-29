from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from nora.domain.base.exceptions import InfrastructureError
from nora.infrastructure.config import Settings
from nora.infrastructure.database import (
    AuditMixin,
    Base,
    SqlAlchemyRepository,
    create_database_engine,
    create_session_factory,
)


class Item(Base, AuditMixin):
    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_database_engine(Settings(), "sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_crud_and_version(session: AsyncSession) -> None:
    repository = SqlAlchemyRepository(session, Item)
    item = await repository.add(Item(name="first"))
    await session.commit()
    assert isinstance(item.id, UUID)
    assert item.version == 1
    assert await repository.get(item.id) is not None

    item.name = "updated"
    updated = await repository.update(item)
    await session.commit()
    assert updated.version == 2
    assert (await repository.list())[0].name == "updated"

    await repository.delete(item.id)
    await session.commit()
    assert await repository.get(item.id) is None


@pytest.mark.asyncio
async def test_repository_rejects_version_conflict(session: AsyncSession) -> None:
    repository = SqlAlchemyRepository(session, Item)
    item = await repository.add(Item(name="first"))
    await session.commit()
    item.version = 99

    with pytest.raises(InfrastructureError, match="Optimistic lock conflict"):
        await repository.update(item)
