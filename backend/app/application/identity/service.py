"""Identity 用例。"""

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.domain.base.exceptions import ErrorCode, NoraError, RateLimitError
from app.domain.identity import User
from app.ports.identity import (
    AccessTokenClaims,
    AuthenticationRateLimitRepository,
    UserRepository,
)

DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$owQAbjQKij7tDQunO6Hdzg$"
    "/s1TV/Con1C44iz72fR1wenHk3qlbcQ9sUULsfSicWA"
)


class PasswordHasher(Protocol):
    """密码哈希端口。"""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class TokenIssuer(Protocol):
    """访问令牌端口。"""

    def issue(self, user_id: UUID, session_version: int = 1) -> str: ...

    def decode(self, token: str) -> "AccessTokenClaims": ...


class IdentifierDigester(Protocol):
    def digest(self, dimension: str, value: str) -> str: ...


class IdentityService:
    """注册、登录和当前用户查询用例。"""

    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_issuer: TokenIssuer,
        rate_limits: AuthenticationRateLimitRepository | None = None,
        digester: IdentifierDigester | None = None,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_issuer = token_issuer
        self.rate_limits = rate_limits
        self.digester = digester

    async def register(self, username: str, email: str, password: str) -> User:
        if not 8 <= len(password) <= 256:
            raise NoraError(
                "Password must contain 8-256 characters", error_code=ErrorCode.INVALID_PASSWORD
            )
        user = User.create(username, email)
        if await self.repository.get_by_username(user.username) is not None:
            raise NoraError(
                "Username is already registered", error_code=ErrorCode.USERNAME_CONFLICT
            )
        if await self.repository.exists_by_email(user.email):
            raise NoraError("Email is already registered", error_code=ErrorCode.EMAIL_CONFLICT)
        stored = await self.repository.add(user, self.password_hasher.hash(password))
        await self.repository.commit()
        return stored

    async def login(self, username: str, password: str, client_identifier: str = "direct") -> str:
        normalized_username = username.strip().lower()
        target_digest: str | None = None
        client_digest: str | None = None
        if self.rate_limits is not None and self.digester is not None:
            target_digest = self.digester.digest("login-target", normalized_username)
            client_digest = self.digester.digest("login-client", client_identifier)
            decision = await self.rate_limits.reserve_login(
                target_digest, client_digest, datetime.now(timezone.utc)
            )
            if not decision.allowed:
                raise RateLimitError("Authentication rate limit exceeded", decision.retry_after)

        credential = await self.repository.get_by_username(normalized_username)
        password_hash = credential.password_hash if credential is not None else DUMMY_PASSWORD_HASH
        verified = self.password_hasher.verify(password, password_hash)
        if credential is None or not verified:
            raise NoraError(
                "Invalid username or password", error_code=ErrorCode.AUTHENTICATION_FAILED
            )
        if self.rate_limits is not None and target_digest is not None and client_digest is not None:
            await self.rate_limits.release_success(
                target_digest, client_digest, datetime.now(timezone.utc)
            )
        return self.token_issuer.issue(credential.user.id, credential.user.session_version)

    async def current_user(self, token: str) -> User:
        claims = self.token_issuer.decode(token)
        user = await self.repository.get_by_id(claims.user_id)
        if user is None or user.session_version != claims.session_version:
            raise NoraError("Authentication required", error_code=ErrorCode.AUTHENTICATION_FAILED)
        return user
