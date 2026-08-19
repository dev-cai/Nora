"""Immutable user-scoped JobFitAnalysis persistence."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.decision import JobFitAnalysis
from app.infrastructure.database.base import Base
from app.infrastructure.database.decision import DecisionReportRecord


class JobFitAnalysisRecord(Base):
    __tablename__ = "job_fit_analyses"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "report_id",
            "version",
            name="uq_job_fit_analysis_report_version",
        ),
        UniqueConstraint(
            "owner_id",
            "generation_identity",
            name="uq_job_fit_analysis_generation",
        ),
        CheckConstraint("version >= 1", name="ck_job_fit_analysis_version"),
        CheckConstraint(
            "length(generation_identity) = 64",
            name="ck_job_fit_analysis_generation_identity",
        ),
        ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_job_fit_analysis_report_owner",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyJobFitAnalysisRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: JobFitAnalysisRecord) -> JobFitAnalysis:
        return JobFitAnalysis.restore(
            analysis_id=record.id,
            owner_id=record.owner_id,
            report_id=record.report_id,
            report_version=record.report_version,
            decision_case_id=record.decision_case_id,
            version=record.version,
            prompt_version=record.prompt_version,
            provider=record.provider,
            model=record.model,
            generator_version=record.generator_version,
            generation_identity=record.generation_identity,
            content=record.content,
            generated_at=_as_utc(record.generated_at),
        )

    async def next_version(self, report_id: UUID) -> int:
        report = await self.session.scalar(
            select(DecisionReportRecord)
            .where(
                DecisionReportRecord.id == report_id,
                DecisionReportRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if report is None:
            raise InfrastructureError(
                "Decision report not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        latest = await self.session.scalar(
            select(func.max(JobFitAnalysisRecord.version)).where(
                JobFitAnalysisRecord.report_id == report_id,
                JobFitAnalysisRecord.owner_id == self.owner_id,
            )
        )
        return (latest or 0) + 1

    async def add(self, analysis: JobFitAnalysis) -> JobFitAnalysis:
        if analysis.owner_id != self.owner_id:
            raise InfrastructureError(
                "Job-fit analysis not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        record = JobFitAnalysisRecord(
            id=analysis.id,
            owner_id=analysis.owner_id,
            report_id=analysis.report_id,
            report_version=analysis.report_version,
            decision_case_id=analysis.decision_case_id,
            version=analysis.version,
            prompt_version=analysis.prompt_version,
            provider=analysis.provider,
            model=analysis.model,
            generator_version=analysis.generator_version,
            generation_identity=analysis.generation_identity,
            content=analysis.content,
            generated_at=analysis.generated_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Job-fit analysis already exists",
                error_code=ErrorCode.DECISION_REPORT_GENERATION_CONFLICT,
            ) from exc
        return self._to_domain(record)

    async def get_by_generation(self, generation_identity: str) -> JobFitAnalysis | None:
        record = await self.session.scalar(
            select(JobFitAnalysisRecord).where(
                JobFitAnalysisRecord.owner_id == self.owner_id,
                JobFitAnalysisRecord.generation_identity == generation_identity,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_for_report(self, report_id: UUID) -> JobFitAnalysis | None:
        record = await self.session.scalar(
            select(JobFitAnalysisRecord)
            .where(
                JobFitAnalysisRecord.owner_id == self.owner_id,
                JobFitAnalysisRecord.report_id == report_id,
            )
            .order_by(JobFitAnalysisRecord.version.desc())
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
