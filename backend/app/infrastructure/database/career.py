"""CandidateProfile 版本化持久化模型和 Repository。"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import InfrastructureError
from app.domain.career import CandidateProfile
from app.infrastructure.database.base import Base
from app.infrastructure.database.identity import UserRecord


class CandidateProfileRecord(Base):
    """一条不可变 CandidateProfile 版本记录。"""

    __tablename__ = "candidate_profile_versions"
    __table_args__ = (
        UniqueConstraint("owner_id", "version", name="uq_candidate_profile_owner_version"),
        CheckConstraint("version >= 1", name="ck_candidate_profile_version_positive"),
    )

    record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    profile_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyCandidateProfileRepository:
    """通过用户行锁串行化主档版本追加。"""

    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: CandidateProfileRecord) -> CandidateProfile:
        return CandidateProfile.restore(
            profile_id=record.profile_id,
            owner_id=record.owner_id,
            version=record.version,
            content=record.content,
            created_at=_as_utc(record.profile_created_at),
            updated_at=_as_utc(record.updated_at),
        )

    async def get_latest(self) -> CandidateProfile | None:
        record = await self.session.scalar(
            select(CandidateProfileRecord)
            .where(CandidateProfileRecord.owner_id == self.owner_id)
            .order_by(CandidateProfileRecord.version.desc())
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def get_version(self, version: int) -> CandidateProfile | None:
        record = await self.session.scalar(
            select(CandidateProfileRecord).where(
                CandidateProfileRecord.owner_id == self.owner_id,
                CandidateProfileRecord.version == version,
            )
        )
        return None if record is None else self._to_domain(record)

    async def add(self, profile: CandidateProfile) -> CandidateProfile:
        if profile.owner_id != self.owner_id:
            raise InfrastructureError(
                "Candidate profile is outside user scope", error_code="entity_not_found"
            )

        await self.session.scalar(
            select(UserRecord.id).where(UserRecord.id == self.owner_id).with_for_update()
        )
        latest = await self.get_latest()
        if latest is None:
            valid_next_version = profile.version == 1
        else:
            valid_next_version = latest.id == profile.id and profile.version == latest.version + 1
        if not valid_next_version:
            raise InfrastructureError(
                "Candidate profile version conflict", error_code="profile_version_conflict"
            )

        record = CandidateProfileRecord(
            profile_id=profile.id,
            owner_id=profile.owner_id,
            version=profile.version,
            content=profile.content,
            profile_created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Candidate profile version conflict", error_code="profile_version_conflict"
            ) from exc
        return self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
