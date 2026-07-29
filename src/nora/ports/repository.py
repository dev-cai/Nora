"""Repository 抽象契约。"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """定义持久化适配器必须实现的异步 CRUD 操作。"""

    @abstractmethod
    async def add(self, entity: T) -> T: ...

    @abstractmethod
    async def get(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    async def list(self, *, offset: int = 0, limit: int = 100) -> list[T]: ...

    @abstractmethod
    async def update(self, entity: T) -> T: ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None: ...
