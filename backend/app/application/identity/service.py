"""Identity 用例。"""

from typing import Protocol
from uuid import UUID

from app.domain.base.exceptions import NoraError
from app.domain.identity import User
from app.ports.identity import UserRepository


class PasswordHasher(Protocol):
    """密码哈希端口。"""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class TokenIssuer(Protocol):
    """访问令牌端口。"""

    def issue(self, user_id: UUID) -> str: ...

    def decode(self, token: str) -> UUID: ...


class IdentityService:
    """注册、登录和当前用户查询用例。"""

    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_issuer: TokenIssuer,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_issuer = token_issuer

    async def register(self, username: str, email: str, password: str) -> User:
        if not 8 <= len(password) <= 256:
            raise NoraError("Password must contain 8-256 characters", error_code="invalid_password")
        user = User.create(username, email)
        if await self.repository.get_by_username(user.username) is not None:
            raise NoraError("Username is already registered", error_code="username_conflict")
        if await self.repository.exists_by_email(user.email):
            raise NoraError("Email is already registered", error_code="email_conflict")
        stored = await self.repository.add(user, self.password_hasher.hash(password))
        await self.repository.commit()
        return stored

    async def login(self, username: str, password: str) -> str:
        credential = await self.repository.get_by_username(username.strip().lower())
        if credential is None or not self.password_hasher.verify(
            password, credential.password_hash
        ):
            raise NoraError("Invalid username or password", error_code="authentication_failed")
        return self.token_issuer.issue(credential.user.id)

    async def current_user(self, token: str) -> User:
        user_id = self.token_issuer.decode(token)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NoraError("Authentication required", error_code="authentication_failed")
        return user
