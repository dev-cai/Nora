"""Identity ORM 模型和 Repository 适配器。"""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    case,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError, NoraError
from app.domain.governance import AuditAction, AuditEvent
from app.domain.identity import User
from app.infrastructure.database.base import AuditMixin, Base
from app.ports.governance import AuditEventRepository
from app.ports.identity import (
    ManagementResult,
    ManagementStatus,
    RateLimitDecision,
    StoredCredential,
)


class UserRecord(Base, AuditMixin):
    """用户持久化记录。"""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("session_version >= 1", name="ck_users_session_version"),)

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BetaOwnerRecord(Base):
    """Production singleton slot referencing the only provisioned owner."""

    __tablename__ = "beta_owner"
    __table_args__ = (CheckConstraint("slot = 1", name="ck_beta_owner_singleton_slot"),)

    slot: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdentityManagementRequestRecord(Base):
    """Idempotency facts for controlled bootstrap and credential recovery."""

    __tablename__ = "identity_management_requests"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('bootstrap', 'recover')", name="ck_identity_management_operation"
        ),
        UniqueConstraint("operation", "request_identity", name="uq_identity_management_request"),
        CheckConstraint(
            "length(identity_fingerprint) = 64",
            name="ck_identity_management_fingerprint",
        ),
        CheckConstraint(
            "resulting_session_version >= 1",
            name="ck_identity_management_session_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    request_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    identity_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resulting_session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthenticationRateLimitRecord(Base):
    """Anonymous, expiring PostgreSQL authentication bucket."""

    __tablename__ = "authentication_rate_limits"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('coarse_client', 'login_target', 'login_client')",
            name="ck_auth_rate_limit_dimension",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_auth_rate_limit_count"),
        CheckConstraint("length(bucket_key) = 64", name="ck_auth_rate_limit_bucket_key"),
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class SqlAlchemyUserRepository:
    """基于 AsyncSession 的用户 Repository。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_user(record: UserRecord) -> User:
        return User(
            id=record.id,
            username=record.username,
            email=record.email,
            session_version=record.session_version,
        )

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


class SqlAlchemyAuthenticationRateLimitRepository:
    """Atomic PostgreSQL buckets; failures never fall back to process memory."""

    COARSE_LIMIT = 30
    LOGIN_TARGET_LIMIT = 5
    LOGIN_CLIENT_LIMIT = 20

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def consume_coarse(self, client_digest: str, now: datetime) -> RateLimitDecision:
        decision = await self._reserve(
            client_digest, "coarse_client", self.COARSE_LIMIT, timedelta(minutes=1), now
        )
        await self.session.commit()
        return decision

    async def reserve_login(
        self, target_digest: str, client_digest: str, now: datetime
    ) -> RateLimitDecision:
        try:
            target = await self._reserve(
                target_digest, "login_target", self.LOGIN_TARGET_LIMIT, timedelta(minutes=15), now
            )
            if not target.allowed:
                await self.session.rollback()
                return target
            client = await self._reserve(
                client_digest, "login_client", self.LOGIN_CLIENT_LIMIT, timedelta(minutes=15), now
            )
            if not client.allowed:
                await self.session.rollback()
                return client
            await self.session.commit()
            return RateLimitDecision(allowed=True, retry_after=0)
        except Exception:
            await self.session.rollback()
            raise

    async def release_success(self, target_digest: str, client_digest: str, now: datetime) -> None:
        await self.session.execute(
            delete(AuthenticationRateLimitRecord).where(
                AuthenticationRateLimitRecord.bucket_key == target_digest,
                AuthenticationRateLimitRecord.dimension == "login_target",
            )
        )
        await self.session.execute(
            update(AuthenticationRateLimitRecord)
            .where(
                AuthenticationRateLimitRecord.bucket_key == client_digest,
                AuthenticationRateLimitRecord.dimension == "login_client",
                AuthenticationRateLimitRecord.expires_at > now,
                AuthenticationRateLimitRecord.attempt_count > 0,
            )
            .values(attempt_count=AuthenticationRateLimitRecord.attempt_count - 1)
        )
        await self.session.commit()

    async def _reserve(
        self,
        bucket_key: str,
        dimension: str,
        limit: int,
        window: timedelta,
        now: datetime,
    ) -> RateLimitDecision:
        current = now.astimezone(timezone.utc)
        expires_at = current + window
        base_statement = insert(AuthenticationRateLimitRecord).values(
            bucket_key=bucket_key,
            dimension=dimension,
            attempt_count=1,
            window_started_at=current,
            expires_at=expires_at,
        )
        statement = base_statement.on_conflict_do_update(
            index_elements=[AuthenticationRateLimitRecord.bucket_key],
            set_={
                "dimension": dimension,
                "attempt_count": case(
                    (AuthenticationRateLimitRecord.expires_at <= current, 1),
                    else_=AuthenticationRateLimitRecord.attempt_count + 1,
                ),
                "window_started_at": case(
                    (AuthenticationRateLimitRecord.expires_at <= current, current),
                    else_=AuthenticationRateLimitRecord.window_started_at,
                ),
                "expires_at": case(
                    (AuthenticationRateLimitRecord.expires_at <= current, expires_at),
                    else_=AuthenticationRateLimitRecord.expires_at,
                ),
            },
            where=(
                (AuthenticationRateLimitRecord.expires_at <= current)
                | (AuthenticationRateLimitRecord.attempt_count < limit)
            ),
        ).returning(AuthenticationRateLimitRecord.expires_at)
        allowed_expiry = await self.session.scalar(statement)
        if allowed_expiry is not None:
            return RateLimitDecision(allowed=True, retry_after=0)

        stored_expiry = await self.session.scalar(
            select(AuthenticationRateLimitRecord.expires_at).where(
                AuthenticationRateLimitRecord.bucket_key == bucket_key
            )
        )
        retry_after = max(1, int(((stored_expiry or expires_at) - current).total_seconds()) + 1)
        return RateLimitDecision(allowed=False, retry_after=retry_after)


class SqlAlchemyIdentityManagementRepository:
    """Serialize management operations with a transaction-scoped PostgreSQL lock."""

    _LOCK_ID = 4_663_191_750

    def __init__(self, session: AsyncSession, audit_events: AuditEventRepository) -> None:
        self.session = session
        self.audit_events = audit_events

    async def bootstrap(
        self,
        user: User,
        password_hash: str,
        request_identity: str,
        identity_fingerprint: str,
    ) -> ManagementResult:
        await self._lock()
        existing = await self._request("bootstrap", request_identity)
        if existing is not None:
            if existing.identity_fingerprint != identity_fingerprint:
                await self.session.rollback()
                raise NoraError(
                    "Management request identity is already used",
                    error_code=ErrorCode.IDEMPOTENCY_CONFLICT,
                )
            await self.session.rollback()
            return ManagementResult(
                ManagementStatus.REPLAYED,
                existing.user_id,
                existing.resulting_session_version,
            )
        provisioned_owner = await self.session.scalar(
            select(BetaOwnerRecord.user_id).where(BetaOwnerRecord.slot == 1)
        )
        if provisioned_owner is not None:
            await self.session.rollback()
            return ManagementResult(ManagementStatus.ALREADY_PROVISIONED, None, None)
        if await self.session.scalar(select(UserRecord.id).limit(1)) is not None:
            await self.session.rollback()
            return ManagementResult(ManagementStatus.ALREADY_PROVISIONED, None, None)

        now = datetime.now(timezone.utc)
        self.session.add(
            UserRecord(
                id=user.id,
                username=user.username,
                email=user.email,
                password_hash=password_hash,
                is_active=True,
                session_version=1,
            )
        )
        await self.session.flush()
        self.session.add(BetaOwnerRecord(slot=1, user_id=user.id, created_at=now))
        self.session.add(
            IdentityManagementRequestRecord(
                id=uuid4(),
                operation="bootstrap",
                request_identity=request_identity,
                identity_fingerprint=identity_fingerprint,
                user_id=user.id,
                resulting_session_version=1,
                created_at=now,
            )
        )
        await self.audit_events.add(
            AuditEvent.create(
                actor_id=user.id,
                action=AuditAction.CREATE,
                target_type="beta_owner",
                target_id=user.id,
                target_version=1,
                after_summary='{"status":"provisioned"}',
                idempotency_key=request_identity,
                now=now,
            )
        )
        await self.session.commit()
        return ManagementResult(ManagementStatus.CREATED, user.id, 1)

    async def recover(self, password_hash: str, request_identity: str) -> ManagementResult:
        await self._lock()
        existing = await self._request("recover", request_identity)
        if existing is not None:
            await self.session.rollback()
            return ManagementResult(
                ManagementStatus.REPLAYED,
                existing.user_id,
                existing.resulting_session_version,
            )
        owner = await self.session.scalar(
            select(UserRecord)
            .join(BetaOwnerRecord, BetaOwnerRecord.user_id == UserRecord.id)
            .where(BetaOwnerRecord.slot == 1, UserRecord.is_active.is_(True))
            .with_for_update()
        )
        if owner is None:
            await self.session.rollback()
            return ManagementResult(ManagementStatus.ALREADY_PROVISIONED, None, None)
        owner.password_hash = password_hash
        owner.session_version += 1
        now = datetime.now(timezone.utc)
        fingerprint = hashlib.sha256(f"owner\0{owner.id}".encode()).hexdigest()
        self.session.add(
            IdentityManagementRequestRecord(
                id=uuid4(),
                operation="recover",
                request_identity=request_identity,
                identity_fingerprint=fingerprint,
                user_id=owner.id,
                resulting_session_version=owner.session_version,
                created_at=now,
            )
        )
        await self.audit_events.add(
            AuditEvent.create(
                actor_id=owner.id,
                action=AuditAction.UPDATE,
                target_type="beta_owner_credentials",
                target_id=owner.id,
                target_version=owner.session_version,
                after_summary='{"status":"credentials_recovered"}',
                idempotency_key=request_identity,
                now=now,
            )
        )
        await self.session.commit()
        return ManagementResult(ManagementStatus.RECOVERED, owner.id, owner.session_version)

    async def _lock(self) -> None:
        await self.session.execute(select(func.pg_advisory_xact_lock(self._LOCK_ID)))

    async def _request(
        self, operation: str, request_identity: str
    ) -> IdentityManagementRequestRecord | None:
        return await self.session.scalar(
            select(IdentityManagementRequestRecord).where(
                IdentityManagementRequestRecord.operation == operation,
                IdentityManagementRequestRecord.request_identity == request_identity,
            )
        )
