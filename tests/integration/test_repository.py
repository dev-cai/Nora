from uuid import UUID, uuid4

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from nora.domain.base.exceptions import InfrastructureError
from nora.infrastructure.database import (
    AuditMixin,
    Base,
    OwnedByUserMixin,
    SqlAlchemyRepository,
    SqlAlchemyUserScopedRepository,
    UserRecord,
)


class Item(Base, AuditMixin):
    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


class OwnedItem(Base, AuditMixin, OwnedByUserMixin):
    __tablename__ = "owned_items"

    name: Mapped[str] = mapped_column(String(100), nullable=False)


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


@pytest.mark.asyncio
async def test_user_scoped_repository_prevents_cross_user_access(session: AsyncSession) -> None:
    owner_a = UserRecord(
        username=f"owner-a-{uuid4()}",
        email=f"owner-a-{uuid4()}@example.com",
        password_hash="hash",
    )
    owner_b = UserRecord(
        username=f"owner-b-{uuid4()}",
        email=f"owner-b-{uuid4()}@example.com",
        password_hash="hash",
    )
    session.add_all([owner_a, owner_b])
    await session.commit()

    repository_a = SqlAlchemyUserScopedRepository(session, OwnedItem, owner_a.id)
    repository_b = SqlAlchemyUserScopedRepository(session, OwnedItem, owner_b.id)
    item = await repository_a.add(OwnedItem(name="private", owner_id=owner_b.id))
    await session.commit()

    assert item.owner_id == owner_a.id
    assert await repository_a.get(item.id) is item
    assert await repository_b.get(item.id) is None
    assert await repository_b.list() == []

    await repository_b.delete(item.id)
    await session.commit()
    assert await repository_a.get(item.id) is not None

    with pytest.raises(InfrastructureError, match="outside user scope"):
        await repository_b.update(item)
