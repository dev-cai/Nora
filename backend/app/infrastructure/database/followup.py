"""ApplicationDecision ORM model and user-scoped repository."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import InfrastructureError
from app.domain.followup import ApplicationDecision, ApplicationDecisionStatus
from app.infrastructure.database.base import Base


class ApplicationDecisionRecord(Base):
    __tablename__ = "application_decisions"
    __table_args__ = (
        UniqueConstraint("owner_id", "report_id", name="uq_application_decision_owner_report"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_application_decision_owner_key"),
        CheckConstraint("report_version >= 1", name="ck_application_decision_report_version"),
        CheckConstraint("resume_version >= 1", name="ck_application_decision_resume_version"),
        CheckConstraint("status IN ('apply', 'skip')", name="ck_application_decision_status"),
        CheckConstraint("actor_id = owner_id", name="ck_application_decision_actor_owner"),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 255",
            name="ck_application_decision_key_length",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_application_decision_fingerprint_length",
        ),
        CheckConstraint(
            "reason IS NULL OR length(reason) <= 1000",
            name="ck_application_decision_reason_length",
        ),
        CheckConstraint(
            "(status = 'skip' AND reason IS NOT NULL AND length(trim(reason)) > 0) OR "
            "(status = 'apply')",
            name="ck_application_decision_skip_reason",
        ),
        ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_application_decision_report_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["decision_case_id", "resume_version_id", "resume_version", "owner_id"],
            [
                "decision_cases.id",
                "decision_cases.resume_version_id",
                "decision_cases.resume_version",
                "decision_cases.owner_id",
            ],
            name="fk_application_decision_case_resume_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_application_decision_resume_owner",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyApplicationDecisionRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: ApplicationDecisionRecord) -> ApplicationDecision:
        return ApplicationDecision.restore(
            decision_id=record.id,
            owner_id=record.owner_id,
            actor_id=record.actor_id,
            report_id=record.report_id,
            report_version=record.report_version,
            decision_case_id=record.decision_case_id,
            resume_version_id=record.resume_version_id,
            resume_version=record.resume_version,
            status=ApplicationDecisionStatus(record.status),
            reason=record.reason,
            idempotency_key=record.idempotency_key,
            request_fingerprint=record.request_fingerprint,
            decided_at=_as_utc(record.decided_at),
        )

    async def add(self, decision: ApplicationDecision) -> ApplicationDecision:
        if decision.owner_id != self.owner_id:
            raise InfrastructureError(
                "Application decision is outside user scope", error_code="entity_not_found"
            )
        record = ApplicationDecisionRecord(
            id=decision.id,
            owner_id=decision.owner_id,
            actor_id=decision.actor_id,
            report_id=decision.report_id,
            report_version=decision.report_version,
            decision_case_id=decision.decision_case_id,
            resume_version_id=decision.resume_version_id,
            resume_version=decision.resume_version,
            status=decision.status.value,
            reason=decision.reason,
            idempotency_key=decision.idempotency_key,
            request_fingerprint=decision.request_fingerprint,
            decided_at=decision.decided_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            error_code = (
                "application_decision_key_taken"
                if constraint == "uq_application_decision_owner_key"
                else "application_decision_conflict"
            )
            raise InfrastructureError(
                "Application decision already exists", error_code=error_code
            ) from exc
        return self._to_domain(record)

    async def get_by_report_id(self, report_id: UUID) -> ApplicationDecision | None:
        record = await self.session.scalar(
            select(ApplicationDecisionRecord).where(
                ApplicationDecisionRecord.owner_id == self.owner_id,
                ApplicationDecisionRecord.report_id == report_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_idempotency_key(self, key: str) -> ApplicationDecision | None:
        record = await self.session.scalar(
            select(ApplicationDecisionRecord).where(
                ApplicationDecisionRecord.owner_id == self.owner_id,
                ApplicationDecisionRecord.idempotency_key == key,
            )
        )
        return None if record is None else self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
