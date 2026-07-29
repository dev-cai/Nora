"""Identity 应用层依赖的 Repository 契约。"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from nora.domain.identity import User


@dataclass(frozen=True, slots=True)
class StoredCredential:
    """供登录校验使用的用户和密码哈希。"""

    user: User
    password_hash: str


class UserRepository(Protocol):
    """用户持久化端口。"""

    async def add(self, user: User, password_hash: str) -> User: ...

    async def get_by_username(self, username: str) -> StoredCredential | None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def exists_by_email(self, email: str) -> bool: ...

    async def commit(self) -> None: ...
