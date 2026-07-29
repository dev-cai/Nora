"""SQLAlchemy Repository 通用实现。"""

from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect

from nora.domain.base.exceptions import InfrastructureError
from nora.ports.repository import Repository

T = TypeVar("T")


class SqlAlchemyRepository(Repository[T], Generic[T]):
    """基于 SQLAlchemy AsyncSession 的通用 CRUD 适配器。"""

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, entity_id: UUID) -> T | None:
        return await self.session.get(self.model, entity_id)

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[T]:
        result = await self.session.scalars(select(self.model).offset(offset).limit(limit))
        return list(result)

    async def update(self, entity: T) -> T:
        state = inspect(entity)
        if not state.identity:
            raise InfrastructureError("Cannot update a transient entity", error_code="entity_not_persisted")
        entity_id = state.identity[0]
        old_version = entity.version
        values = {
            column.key: getattr(entity, column.key)
            for column in inspect(self.model).mapper.column_attrs
            if column.key not in {"id", "version", "created_at", "updated_at"}
        }
        values["updated_at"] = datetime.now(timezone.utc)
        values["version"] = old_version + 1
        with self.session.no_autoflush:
            result = await self.session.execute(
                sql_update(self.model)
                .where(self.model.id == entity_id, self.model.version == old_version)
                .values(**values)
            )
        if result.rowcount != 1:
            raise InfrastructureError("Optimistic lock conflict", error_code="version_conflict")
        entity.version = old_version + 1
        entity.updated_at = values["updated_at"]
        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> None:
        await self.session.execute(sql_delete(self.model).where(self.model.id == entity_id))
        await self.session.flush()
