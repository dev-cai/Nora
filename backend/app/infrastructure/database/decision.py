"""DecisionCase ORM 模型和用户范围 Repository。"""

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

from app.domain.base.exceptions import InfrastructureError
from app.domain.decision import (
    CompanyAssessment,
    CompanyAssessmentStatus,
    DecisionCase,
    DecisionCaseStatus,
    DecisionReport,
)
from app.infrastructure.database.base import Base


class DecisionCaseRecord(Base):
    """固定全部输入版本的一条决策案例记录。"""

    __tablename__ = "decision_cases"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_decision_case_id_owner"),
        UniqueConstraint(
            "id",
            "resume_version_id",
            "resume_version",
            "owner_id",
            name="uq_decision_case_resume_owner",
        ),
        UniqueConstraint(
            "id",
            "job_posting_id",
            "job_posting_version",
            "owner_id",
            name="uq_decision_case_job_owner",
        ),
        UniqueConstraint(
            "id",
            "job_requirement_snapshot_id",
            "job_requirement_snapshot_version",
            "owner_id",
            name="uq_decision_case_requirement_owner",
        ),
        UniqueConstraint(
            "owner_id", "input_fingerprint", name="uq_decision_case_owner_fingerprint"
        ),
        CheckConstraint("job_posting_version >= 1", name="ck_decision_job_version_positive"),
        CheckConstraint(
            "job_requirement_snapshot_version >= 1",
            name="ck_decision_requirement_version_positive",
        ),
        CheckConstraint(
            "candidate_profile_version >= 1", name="ck_decision_profile_version_positive"
        ),
        CheckConstraint("resume_version >= 1", name="ck_decision_resume_version_positive"),
        CheckConstraint("status IN ('created', 'completed', 'failed')", name="ck_decision_status"),
        CheckConstraint(
            "(status = 'created' AND completed_at IS NULL AND failure_code IS NULL "
            "AND failure_message IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL AND failure_code IS NULL "
            "AND failure_message IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND failure_code IS NOT NULL "
            "AND failure_message IS NOT NULL)",
            name="ck_decision_terminal_state",
        ),
        ForeignKeyConstraint(
            ["job_posting_id", "job_posting_version", "owner_id"],
            ["job_postings.id", "job_postings.version", "job_postings.owner_id"],
            name="fk_decision_case_job_input",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["job_requirement_snapshot_id", "job_requirement_snapshot_version", "owner_id"],
            [
                "job_requirement_snapshots.snapshot_id",
                "job_requirement_snapshots.version",
                "job_requirement_snapshots.owner_id",
            ],
            name="fk_decision_case_requirement_input",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["candidate_profile_id", "candidate_profile_version", "owner_id"],
            [
                "candidate_profile_versions.profile_id",
                "candidate_profile_versions.version",
                "candidate_profile_versions.owner_id",
            ],
            name="fk_decision_case_profile_input",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_decision_case_resume_input",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_posting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_posting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_requirement_snapshot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_requirement_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    candidate_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1_000), nullable=True)


class DecisionReportRecord(Base):
    """不可变、可追溯且按生成身份幂等的决策报告。"""

    __tablename__ = "decision_reports"
    __table_args__ = (
        UniqueConstraint("id", "version", "owner_id", name="uq_decision_report_id_version_owner"),
        UniqueConstraint(
            "id",
            "version",
            "decision_case_id",
            "owner_id",
            name="uq_decision_report_case_identity",
        ),
        UniqueConstraint(
            "decision_case_id",
            "version",
            name="uq_decision_report_case_version",
        ),
        UniqueConstraint(
            "owner_id",
            "decision_case_id",
            "rule_set_version",
            "generator_version",
            name="uq_decision_report_generation",
        ),
        CheckConstraint("version >= 1", name="ck_decision_report_version_positive"),
        ForeignKeyConstraint(
            ["decision_case_id", "owner_id"],
            ["decision_cases.id", "decision_cases.owner_id"],
            name="fk_decision_report_case_owner",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyAssessmentRecord(Base):
    """A fixed company attachment for one exact report version."""

    __tablename__ = "company_assessments"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "report_id",
            "report_version",
            name="uq_company_assessment_report",
        ),
        UniqueConstraint(
            "owner_id", "generation_identity", name="uq_company_assessment_generation"
        ),
        CheckConstraint("version >= 1", name="ck_company_assessment_version"),
        CheckConstraint("decision_case_version >= 1", name="ck_company_assessment_case_version"),
        CheckConstraint(
            "company_snapshot_version >= 1", name="ck_company_assessment_snapshot_version"
        ),
        CheckConstraint(
            "decision_case_version = 1", name="ck_company_assessment_case_compat_version"
        ),
        CheckConstraint(
            "length(generation_identity) = 64", name="ck_company_assessment_generation_identity"
        ),
        CheckConstraint(
            "status IN ('available', 'unknown', 'conflicted', 'stale')",
            name="ck_company_assessment_status",
        ),
        ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_company_assessment_report_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["decision_case_id", "owner_id"],
            ["decision_cases.id", "decision_cases.owner_id"],
            name="fk_company_assessment_case_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["company_snapshot_id", "company_snapshot_version", "owner_id"],
            [
                "company_snapshots.snapshot_id",
                "company_snapshots.version",
                "company_snapshots.owner_id",
            ],
            name="fk_company_assessment_snapshot_owner",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    company_snapshot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    company_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_reason: Mapped[str] = mapped_column(String(200), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyDecisionCaseRepository:
    """用户范围内持久化并读取 DecisionCase。"""

    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: DecisionCaseRecord) -> DecisionCase:
        return DecisionCase.restore(
            case_id=record.id,
            owner_id=record.owner_id,
            job_posting_id=record.job_posting_id,
            job_posting_version=record.job_posting_version,
            job_requirement_snapshot_id=record.job_requirement_snapshot_id,
            job_requirement_snapshot_version=record.job_requirement_snapshot_version,
            candidate_profile_id=record.candidate_profile_id,
            candidate_profile_version=record.candidate_profile_version,
            resume_version_id=record.resume_version_id,
            resume_version=record.resume_version,
            rule_set_version=record.rule_set_version,
            input_fingerprint=record.input_fingerprint,
            status=DecisionCaseStatus(record.status),
            created_at=_as_utc(record.created_at),
            completed_at=None if record.completed_at is None else _as_utc(record.completed_at),
            failure_code=record.failure_code,
            failure_message=record.failure_message,
        )

    async def add(self, decision_case: DecisionCase) -> DecisionCase:
        if decision_case.owner_id != self.owner_id:
            raise InfrastructureError(
                "Decision case is outside user scope", error_code="entity_not_found"
            )
        record = DecisionCaseRecord(
            id=decision_case.id,
            owner_id=decision_case.owner_id,
            job_posting_id=decision_case.job_posting_id,
            job_posting_version=decision_case.job_posting_version,
            job_requirement_snapshot_id=decision_case.job_requirement_snapshot_id,
            job_requirement_snapshot_version=decision_case.job_requirement_snapshot_version,
            candidate_profile_id=decision_case.candidate_profile_id,
            candidate_profile_version=decision_case.candidate_profile_version,
            resume_version_id=decision_case.resume_version_id,
            resume_version=decision_case.resume_version,
            rule_set_version=decision_case.rule_set_version,
            input_fingerprint=decision_case.input_fingerprint,
            status=decision_case.status.value,
            created_at=decision_case.created_at,
            completed_at=decision_case.completed_at,
            failure_code=decision_case.failure_code,
            failure_message=decision_case.failure_message,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Decision case input already exists", error_code="decision_case_conflict"
            ) from exc
        return self._to_domain(record)

    async def update(self, decision_case: DecisionCase) -> DecisionCase:
        if decision_case.owner_id != self.owner_id:
            raise InfrastructureError(
                "Decision case is outside user scope", error_code="entity_not_found"
            )
        record = await self.session.scalar(
            select(DecisionCaseRecord)
            .where(
                DecisionCaseRecord.id == decision_case.id,
                DecisionCaseRecord.owner_id == self.owner_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if record is None:
            raise InfrastructureError("Decision case not found", error_code="entity_not_found")
        if not _has_same_fixed_inputs(record, decision_case):
            raise InfrastructureError(
                "Decision case inputs are immutable", error_code="decision_case_immutable"
            )
        if (
            DecisionCaseStatus(record.status) is not DecisionCaseStatus.CREATED
            or decision_case.status is DecisionCaseStatus.CREATED
        ):
            raise InfrastructureError(
                "Decision case has already finished",
                error_code="invalid_decision_case_state",
            )

        record.status = decision_case.status.value
        record.completed_at = decision_case.completed_at
        record.failure_code = decision_case.failure_code
        record.failure_message = decision_case.failure_message
        await self.session.flush()
        return self._to_domain(record)

    async def get_by_id(self, case_id: UUID) -> DecisionCase | None:
        record = await self.session.scalar(
            select(DecisionCaseRecord).where(
                DecisionCaseRecord.id == case_id,
                DecisionCaseRecord.owner_id == self.owner_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_input_fingerprint(self, fingerprint: str) -> DecisionCase | None:
        record = await self.session.scalar(
            select(DecisionCaseRecord).where(
                DecisionCaseRecord.owner_id == self.owner_id,
                DecisionCaseRecord.input_fingerprint == fingerprint,
            )
        )
        return None if record is None else self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()


class SqlAlchemyDecisionReportRepository:
    """用户范围内持久化不可变 DecisionReport。"""

    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: DecisionReportRecord) -> DecisionReport:
        return DecisionReport.restore(
            report_id=record.id,
            owner_id=record.owner_id,
            decision_case_id=record.decision_case_id,
            version=record.version,
            rule_set_version=record.rule_set_version,
            generator_version=record.generator_version,
            content=record.content,
            generated_at=_as_utc(record.generated_at),
        )

    async def next_version(self, decision_case_id: UUID) -> int:
        decision_case = await self.session.scalar(
            select(DecisionCaseRecord)
            .where(
                DecisionCaseRecord.id == decision_case_id,
                DecisionCaseRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if decision_case is None:
            raise InfrastructureError("Decision case not found", error_code="entity_not_found")
        latest_version = await self.session.scalar(
            select(func.max(DecisionReportRecord.version)).where(
                DecisionReportRecord.decision_case_id == decision_case_id,
                DecisionReportRecord.owner_id == self.owner_id,
            )
        )
        return (latest_version or 0) + 1

    async def add(self, report: DecisionReport) -> DecisionReport:
        if report.owner_id != self.owner_id:
            raise InfrastructureError(
                "Decision report is outside user scope", error_code="entity_not_found"
            )
        record = DecisionReportRecord(
            id=report.id,
            owner_id=report.owner_id,
            decision_case_id=report.decision_case_id,
            version=report.version,
            rule_set_version=report.rule_set_version,
            generator_version=report.generator_version,
            content=report.content,
            generated_at=report.generated_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            error_code = (
                "decision_report_generation_conflict"
                if constraint == "uq_decision_report_generation"
                else "decision_report_version_conflict"
            )
            raise InfrastructureError(
                "Decision report already exists", error_code=error_code
            ) from exc
        return self._to_domain(record)

    async def get_by_generation(
        self,
        decision_case_id: UUID,
        rule_set_version: str,
        generator_version: str,
    ) -> DecisionReport | None:
        record = await self.session.scalar(
            select(DecisionReportRecord).where(
                DecisionReportRecord.owner_id == self.owner_id,
                DecisionReportRecord.decision_case_id == decision_case_id,
                DecisionReportRecord.rule_set_version == rule_set_version,
                DecisionReportRecord.generator_version == generator_version,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_id(self, report_id: UUID) -> DecisionReport | None:
        record = await self.session.scalar(
            select(DecisionReportRecord).where(
                DecisionReportRecord.id == report_id,
                DecisionReportRecord.owner_id == self.owner_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def list_for_case(self, decision_case_id: UUID) -> list[DecisionReport]:
        records = await self.session.scalars(
            select(DecisionReportRecord)
            .where(
                DecisionReportRecord.decision_case_id == decision_case_id,
                DecisionReportRecord.owner_id == self.owner_id,
            )
            .order_by(DecisionReportRecord.version)
        )
        return [self._to_domain(record) for record in records]

    async def list(self, *, offset: int, limit: int) -> list[DecisionReport]:
        records = await self.session.scalars(
            select(DecisionReportRecord)
            .where(DecisionReportRecord.owner_id == self.owner_id)
            .order_by(
                DecisionReportRecord.generated_at.desc(),
                DecisionReportRecord.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return [self._to_domain(record) for record in records]

    async def count(self) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(DecisionReportRecord)
            .where(DecisionReportRecord.owner_id == self.owner_id)
        )
        return int(total or 0)

    async def commit(self) -> None:
        await self.session.commit()


class SqlAlchemyCompanyAssessmentRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: CompanyAssessmentRecord) -> CompanyAssessment:
        return CompanyAssessment(
            id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            report_id=record.report_id,
            report_version=record.report_version,
            decision_case_id=record.decision_case_id,
            decision_case_version=record.decision_case_version,
            company_snapshot_id=record.company_snapshot_id,
            company_snapshot_version=record.company_snapshot_version,
            status=CompanyAssessmentStatus(record.status),
            status_reason=record.status_reason,
            generator_version=record.generator_version,
            generation_identity=record.generation_identity,
            created_at=_as_utc(record.assessment_created_at),
        )

    async def add(self, assessment: CompanyAssessment) -> CompanyAssessment:
        if assessment.owner_id != self.owner_id:
            raise InfrastructureError("Company assessment not found", error_code="entity_not_found")
        record = CompanyAssessmentRecord(
            id=assessment.id,
            owner_id=assessment.owner_id,
            version=assessment.version,
            report_id=assessment.report_id,
            report_version=assessment.report_version,
            decision_case_id=assessment.decision_case_id,
            decision_case_version=assessment.decision_case_version,
            company_snapshot_id=assessment.company_snapshot_id,
            company_snapshot_version=assessment.company_snapshot_version,
            status=assessment.status.value,
            status_reason=assessment.status_reason,
            generator_version=assessment.generator_version,
            generation_identity=assessment.generation_identity,
            assessment_created_at=assessment.created_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Company assessment already exists",
                error_code="company_assessment_conflict",
            ) from exc
        return self._to_domain(record)

    async def get_by_generation(self, generation_identity: str) -> CompanyAssessment | None:
        record = await self.session.scalar(
            select(CompanyAssessmentRecord).where(
                CompanyAssessmentRecord.owner_id == self.owner_id,
                CompanyAssessmentRecord.generation_identity == generation_identity,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_for_report(self, report_id: UUID) -> CompanyAssessment | None:
        record = await self.session.scalar(
            select(CompanyAssessmentRecord).where(
                CompanyAssessmentRecord.owner_id == self.owner_id,
                CompanyAssessmentRecord.report_id == report_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()


def _has_same_fixed_inputs(record: DecisionCaseRecord, decision_case: DecisionCase) -> bool:
    return (
        record.owner_id == decision_case.owner_id
        and record.job_posting_id == decision_case.job_posting_id
        and record.job_posting_version == decision_case.job_posting_version
        and record.job_requirement_snapshot_id == decision_case.job_requirement_snapshot_id
        and record.job_requirement_snapshot_version
        == decision_case.job_requirement_snapshot_version
        and record.candidate_profile_id == decision_case.candidate_profile_id
        and record.candidate_profile_version == decision_case.candidate_profile_version
        and record.resume_version_id == decision_case.resume_version_id
        and record.resume_version == decision_case.resume_version
        and record.rule_set_version == decision_case.rule_set_version
        and record.input_fingerprint == decision_case.input_fingerprint
        and _as_utc(record.created_at) == decision_case.created_at
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
