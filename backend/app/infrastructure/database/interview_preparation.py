"""Persistence adapter for immutable interview preparation versions."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.followup import InterviewPreparation
from app.infrastructure.database.base import Base


class InterviewPreparationRecord(Base):
    __tablename__ = "interview_preparations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "interview_case_id", "version", name="uq_interview_preparation_version"
        ),
        ForeignKeyConstraint(
            ["interview_case_id", "interview_case_version", "owner_id"],
            ["interview_cases.id", "interview_cases.version", "interview_cases.owner_id"],
            name="fk_interview_preparation_case_owner",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interview_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    interview_case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    application_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_report_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision_report_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyInterviewPreparationRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: InterviewPreparationRecord) -> InterviewPreparation:
        return InterviewPreparation.restore(
            preparation_id=record.id,
            owner_id=record.owner_id,
            interview_case_id=record.interview_case_id,
            interview_case_version=record.interview_case_version,
            application_record_id=record.application_record_id,
            decision_case_id=record.decision_case_id,
            decision_report_id=record.decision_report_id,
            decision_report_version=record.decision_report_version,
            version=record.version,
            generator_version=record.generator_version,
            prompt_version=record.prompt_version,
            generation_identity=record.generation_identity,
            content=record.content,
            created_at=_utc(record.created_at),
        )

    async def next_version(self, interview_case_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(InterviewPreparationRecord.version)).where(
                InterviewPreparationRecord.owner_id == self.owner_id,
                InterviewPreparationRecord.interview_case_id == interview_case_id,
            )
        )
        return int(latest or 0) + 1

    async def add(self, preparation: InterviewPreparation) -> InterviewPreparation:
        if preparation.owner_id != self.owner_id:
            raise InfrastructureError(
                "Preparation is outside user scope", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        record = InterviewPreparationRecord(
            id=preparation.id,
            owner_id=preparation.owner_id,
            interview_case_id=preparation.interview_case_id,
            interview_case_version=preparation.interview_case_version,
            application_record_id=preparation.application_record_id,
            decision_case_id=preparation.decision_case_id,
            decision_report_id=preparation.decision_report_id,
            decision_report_version=preparation.decision_report_version,
            version=preparation.version,
            generator_version=preparation.generator_version,
            prompt_version=preparation.prompt_version,
            generation_identity=preparation.generation_identity,
            content=preparation.content,
            created_at=preparation.created_at,
        )
        self.session.add(record)
        await self.session.flush()
        return self._to_domain(record)

    async def get_latest(self, interview_case_id: UUID) -> InterviewPreparation | None:
        record = await self.session.scalar(
            select(InterviewPreparationRecord)
            .where(
                InterviewPreparationRecord.owner_id == self.owner_id,
                InterviewPreparationRecord.interview_case_id == interview_case_id,
            )
            .order_by(InterviewPreparationRecord.version.desc())
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def get_version(
        self, interview_case_id: UUID, version: int
    ) -> InterviewPreparation | None:
        record = await self.session.scalar(
            select(InterviewPreparationRecord).where(
                InterviewPreparationRecord.owner_id == self.owner_id,
                InterviewPreparationRecord.interview_case_id == interview_case_id,
                InterviewPreparationRecord.version == version,
            )
        )
        return None if record is None else self._to_domain(record)

    async def list_versions(self, interview_case_id: UUID) -> list[InterviewPreparation]:
        records = await self.session.scalars(
            select(InterviewPreparationRecord)
            .where(
                InterviewPreparationRecord.owner_id == self.owner_id,
                InterviewPreparationRecord.interview_case_id == interview_case_id,
            )
            .order_by(InterviewPreparationRecord.version.desc())
        )
        return [self._to_domain(record) for record in records]

    async def commit(self) -> None:
        await self.session.commit()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
