"""SQLAlchemy Repository 通用实现。"""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy import update as sql_update
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

    def _scope_predicates(self) -> tuple[Any, ...]:
        return ()

    def _prepare_for_add(self, entity: T) -> None:
        pass

    def _validate_for_update(self, entity: T) -> None:
        pass

    def _excluded_update_fields(self) -> set[str]:
        return {"id", "version", "created_at", "updated_at"}

    async def add(self, entity: T) -> T:
        self._prepare_for_add(entity)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, entity_id: UUID) -> T | None:
        dynamic_model = cast(Any, self.model)
        return await self.session.scalar(
            select(self.model).where(
                dynamic_model.id == entity_id,
                *self._scope_predicates(),
            )
        )

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[T]:
        result = await self.session.scalars(
            select(self.model).where(*self._scope_predicates()).offset(offset).limit(limit)
        )
        return list(result)

    async def update(self, entity: T) -> T:
        self._validate_for_update(entity)
        dynamic_entity = cast(Any, entity)
        dynamic_model = cast(Any, self.model)
        state = cast(Any, inspect(dynamic_entity))
        if not state.identity:
            raise InfrastructureError(
                "Cannot update a transient entity", error_code="entity_not_persisted"
            )
        entity_id = state.identity[0]
        old_version = dynamic_entity.version
        mapper = cast(Any, inspect(dynamic_model).mapper)
        values = {
            column.key: getattr(entity, column.key)
            for column in mapper.column_attrs
            if column.key not in self._excluded_update_fields()
        }
        values["updated_at"] = datetime.now(timezone.utc)
        values["version"] = old_version + 1
        with self.session.no_autoflush:
            result = await self.session.execute(
                sql_update(dynamic_model)
                .where(
                    dynamic_model.id == entity_id,
                    dynamic_model.version == old_version,
                    *self._scope_predicates(),
                )
                .values(**values)
            )
        if cast(Any, result).rowcount != 1:
            raise InfrastructureError("Optimistic lock conflict", error_code="version_conflict")
        dynamic_entity.version = old_version + 1
        dynamic_entity.updated_at = values["updated_at"]
        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> None:
        dynamic_model = cast(Any, self.model)
        await self.session.execute(
            sql_delete(dynamic_model).where(
                dynamic_model.id == entity_id,
                *self._scope_predicates(),
            )
        )
        await self.session.flush()


class SqlAlchemyUserScopedRepository(SqlAlchemyRepository[T], Generic[T]):
    """自动把所有持久化操作限制在一个已认证用户范围内。"""

    def __init__(self, session: AsyncSession, model: type[T], owner_id: UUID) -> None:
        if not hasattr(model, "owner_id"):
            raise TypeError("User-scoped models must define owner_id")
        super().__init__(session, model)
        self.owner_id = owner_id

    def _scope_predicates(self) -> tuple[Any, ...]:
        return (cast(Any, self.model).owner_id == self.owner_id,)

    def _prepare_for_add(self, entity: T) -> None:
        setattr(entity, "owner_id", self.owner_id)

    def _validate_for_update(self, entity: T) -> None:
        if getattr(entity, "owner_id", None) != self.owner_id:
            raise InfrastructureError("Entity is outside user scope", error_code="entity_not_found")

    def _excluded_update_fields(self) -> set[str]:
        return super()._excluded_update_fields() | {"owner_id"}
