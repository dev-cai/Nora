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
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import InfrastructureError
from app.domain.decision import DecisionCase, DecisionCaseStatus
from app.infrastructure.database.base import Base


class DecisionCaseRecord(Base):
    """固定全部输入版本的一条决策案例记录。"""

    __tablename__ = "decision_cases"
    __table_args__ = (
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
