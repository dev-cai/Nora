"""Identity ORM 模型和 Repository 适配器。"""

from uuid import UUID

from sqlalchemy import Boolean, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base.exceptions import ErrorCode, InfrastructureError, NoraError
from app.domain.identity import User
from app.infrastructure.database.base import AuditMixin, Base
from app.ports.identity import StoredCredential


class UserRecord(Base, AuditMixin):
    """用户持久化记录。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SqlAlchemyUserRepository:
    """基于 AsyncSession 的用户 Repository。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_user(record: UserRecord) -> User:
        return User(id=record.id, username=record.username, email=record.email)

    async def add(self, user: User, password_hash: str) -> User:
        self.session.add(
            UserRecord(
                id=user.id,
                username=user.username,
                email=user.email,
                password_hash=password_hash,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            if await self._exists_by_username(user.username):
                raise NoraError(
                    "Username is already registered", error_code=ErrorCode.USERNAME_CONFLICT
                ) from exc
            if await self.exists_by_email(user.email):
                raise NoraError(
                    "Email is already registered", error_code=ErrorCode.EMAIL_CONFLICT
                ) from exc
            raise InfrastructureError(
                "Could not persist user", error_code=ErrorCode.IDENTITY_PERSISTENCE_FAILED
            ) from exc
        return user

    async def get_by_username(self, username: str) -> StoredCredential | None:
        record = await self.session.scalar(
            select(UserRecord).where(
                UserRecord.username == username,
                UserRecord.is_active.is_(True),
            )
        )
        if record is None:
            return None
        return StoredCredential(user=self._to_user(record), password_hash=record.password_hash)

    async def _exists_by_username(self, username: str) -> bool:
        return (
            await self.session.scalar(
                select(UserRecord.id).where(UserRecord.username == username).limit(1)
            )
            is not None
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        record = await self.session.get(UserRecord, user_id)
        return None if record is None or not record.is_active else self._to_user(record)

    async def exists_by_email(self, email: str) -> bool:
        return (
            await self.session.scalar(
                select(UserRecord.id).where(UserRecord.email == email).limit(1)
            )
            is not None
        )

    async def commit(self) -> None:
        await self.session.commit()
