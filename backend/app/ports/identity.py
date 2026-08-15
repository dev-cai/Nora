"""Identity 应用层依赖的 Repository 契约。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain.identity import User


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    session_version: int
    kid: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UUID):
            return self.user_id == other
        if isinstance(other, AccessTokenClaims):
            return (
                self.user_id == other.user_id
                and self.session_version == other.session_version
                and self.kid == other.kid
            )
        return NotImplemented


class ManagementStatus(StrEnum):
    CREATED = "created"
    REPLAYED = "replayed"
    ALREADY_PROVISIONED = "already_provisioned"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class ManagementResult:
    status: ManagementStatus
    user_id: UUID | None
    session_version: int | None


@dataclass(frozen=True, slots=True)
class StoredCredential:
    """供登录校验使用的用户和密码哈希。"""

    user: User
    password_hash: str


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """One PostgreSQL rate-limit operation result."""

    allowed: bool
    retry_after: int


class AuthenticationRateLimitRepository(Protocol):
    """Persistent coarse and login-failure rate-limit state."""

    async def consume_coarse(self, client_digest: str, now: datetime) -> RateLimitDecision: ...

    async def reserve_login(
        self, target_digest: str, client_digest: str, now: datetime
    ) -> RateLimitDecision: ...

    async def release_success(
        self, target_digest: str, client_digest: str, now: datetime
    ) -> None: ...


class UserRepository(Protocol):
    """用户持久化端口。"""

    async def add(self, user: User, password_hash: str) -> User: ...

    async def get_by_username(self, username: str) -> StoredCredential | None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def exists_by_email(self, email: str) -> bool: ...

    async def commit(self) -> None: ...
