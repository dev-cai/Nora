"""Application & Follow-up ORM models and user-scoped repositories."""

from datetime import datetime, timezone
from typing import Sequence, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.followup import (
    ApplicationDecision,
    ApplicationDecisionStatus,
    ApplicationRecord,
    ApplicationRecordStatus,
    ApplicationRecordTransition,
    ApplicationTransitionSource,
    MessageDraft,
    MessageDraftRevisionType,
    MessageDraftSource,
    MessageDraftStyle,
    ResumePdf,
    ResumePdfStatus,
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)
from app.infrastructure.database.base import Base


class ApplicationDecisionRecord(Base):
    __tablename__ = "application_decisions"
    __table_args__ = (
        UniqueConstraint("owner_id", "report_id", name="uq_application_decision_owner_report"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_application_decision_owner_key"),
        UniqueConstraint(
            "id",
            "decision_case_id",
            "resume_version_id",
            "resume_version",
            "owner_id",
            name="uq_application_decision_variant_input",
        ),
        UniqueConstraint(
            "id",
            "decision_case_id",
            "owner_id",
            name="uq_application_decision_record_input",
        ),
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
                "Application decision is outside user scope", error_code=ErrorCode.ENTITY_NOT_FOUND
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
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            error_code = (
                ErrorCode.APPLICATION_DECISION_KEY_TAKEN
                if constraint == "uq_application_decision_owner_key"
                else ErrorCode.APPLICATION_DECISION_CONFLICT
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

    async def get_by_id(self, decision_id: UUID) -> ApplicationDecision | None:
        record = await self.session.scalar(
            select(ApplicationDecisionRecord).where(
                ApplicationDecisionRecord.owner_id == self.owner_id,
                ApplicationDecisionRecord.id == decision_id,
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


class TemplateDefinitionRecord(Base):
    __tablename__ = "template_definitions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_definition_identity"),
        CheckConstraint("version >= 1", name="ck_template_definition_version"),
        CheckConstraint("length(definition_hash) = 64", name="ck_template_definition_hash"),
        CheckConstraint("jsonb_typeof(definition) = 'object'", name="ck_template_definition_json"),
    )

    record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    template_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResumeVariantRecord(Base):
    __tablename__ = "resume_variants"
    __table_args__ = (
        UniqueConstraint("id", "version", "owner_id", name="uq_resume_variant_identity"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_resume_variant_owner_key"),
        CheckConstraint("version >= 1", name="ck_resume_variant_version"),
        CheckConstraint("job_posting_version >= 1", name="ck_resume_variant_job_version"),
        CheckConstraint(
            "job_requirement_snapshot_version >= 1",
            name="ck_resume_variant_requirement_version",
        ),
        CheckConstraint("resume_version >= 1", name="ck_resume_variant_resume_version"),
        CheckConstraint("template_version >= 1", name="ck_resume_variant_template_version"),
        CheckConstraint("jsonb_typeof(blocks) = 'array'", name="ck_resume_variant_blocks"),
        CheckConstraint("length(content_fingerprint) = 64", name="ck_resume_variant_fingerprint"),
        ForeignKeyConstraint(
            [
                "application_decision_id",
                "decision_case_id",
                "resume_version_id",
                "resume_version",
                "owner_id",
            ],
            [
                "application_decisions.id",
                "application_decisions.decision_case_id",
                "application_decisions.resume_version_id",
                "application_decisions.resume_version",
                "application_decisions.owner_id",
            ],
            name="fk_resume_variant_apply_decision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["decision_case_id", "job_posting_id", "job_posting_version", "owner_id"],
            [
                "decision_cases.id",
                "decision_cases.job_posting_id",
                "decision_cases.job_posting_version",
                "decision_cases.owner_id",
            ],
            name="fk_resume_variant_job_input",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "decision_case_id",
                "job_requirement_snapshot_id",
                "job_requirement_snapshot_version",
                "owner_id",
            ],
            [
                "decision_cases.id",
                "decision_cases.job_requirement_snapshot_id",
                "decision_cases.job_requirement_snapshot_version",
                "decision_cases.owner_id",
            ],
            name="fk_resume_variant_requirement_input",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_resume_variant_resume_input",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["template_definitions.template_id", "template_definitions.version"],
            name="fk_resume_variant_template_input",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    application_decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_posting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_posting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_requirement_snapshot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_requirement_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    blocks: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResumePdfRecord(Base):
    __tablename__ = "resume_pdfs"
    __table_args__ = (
        UniqueConstraint("id", "version", "owner_id", name="uq_resume_pdf_identity"),
        UniqueConstraint("owner_id", "generation_identity", name="uq_resume_pdf_owner_generation"),
        CheckConstraint("version >= 1", name="ck_resume_pdf_version"),
        CheckConstraint("resume_variant_version >= 1", name="ck_resume_pdf_variant_version"),
        CheckConstraint("template_version >= 1", name="ck_resume_pdf_template_version"),
        CheckConstraint(
            "length(template_definition_hash) = 64", name="ck_resume_pdf_template_hash"
        ),
        CheckConstraint(
            "length(variant_content_fingerprint) = 64",
            name="ck_resume_pdf_variant_fingerprint",
        ),
        CheckConstraint(
            "length(generation_identity) = 64", name="ck_resume_pdf_generation_identity"
        ),
        CheckConstraint(
            "status IN ('pending', 'available', 'failed')", name="ck_resume_pdf_status"
        ),
        CheckConstraint(
            "(status = 'available' AND artifact_id IS NOT NULL "
            "AND artifact_version IS NOT NULL AND artifact_version >= 1 "
            "AND artifact_sha256 IS NOT NULL AND length(artifact_sha256) = 64 "
            "AND artifact_size_bytes IS NOT NULL AND artifact_size_bytes > 0) OR "
            "(status <> 'available' AND artifact_id IS NULL "
            "AND artifact_version IS NULL AND artifact_sha256 IS NULL "
            "AND artifact_size_bytes IS NULL)",
            name="ck_resume_pdf_artifact_state",
        ),
        ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_resume_pdf_variant_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["template_definitions.template_id", "template_definitions.version"],
            name="fk_resume_pdf_template",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_resume_pdf_artifact_owner",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_variant_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    variant_content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    font_set_version: Mapped[str] = mapped_column(String(100), nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pdf_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageDraftRecord(Base):
    __tablename__ = "message_drafts"
    __table_args__ = (
        UniqueConstraint("id", "version", "owner_id", name="uq_message_draft_identity"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_message_draft_owner_key"),
        Index(
            "uq_message_draft_owner_generation",
            "owner_id",
            "generation_identity",
            unique=True,
            postgresql_where=text("version = 1"),
        ),
        CheckConstraint("version >= 1", name="ck_message_draft_version"),
        CheckConstraint("report_version >= 1", name="ck_message_draft_report_version"),
        CheckConstraint("resume_variant_version >= 1", name="ck_message_draft_variant_version"),
        CheckConstraint("candidate_profile_version >= 1", name="ck_message_draft_profile_version"),
        CheckConstraint("resume_version >= 1", name="ck_message_draft_resume_version"),
        CheckConstraint("job_posting_version >= 1", name="ck_message_draft_job_version"),
        CheckConstraint(
            "style IN ('professional', 'concise', 'referral')",
            name="ck_message_draft_style",
        ),
        CheckConstraint(
            "revision_type IN ('generated', 'edited')",
            name="ck_message_draft_revision_type",
        ),
        CheckConstraint(
            "(version = 1 AND revision_type = 'generated' AND previous_version IS NULL) OR "
            "(version > 1 AND revision_type = 'edited' AND previous_version = version - 1)",
            name="ck_message_draft_revision_chain",
        ),
        CheckConstraint(
            "(style = 'referral' AND referral_context IS NOT NULL) OR "
            "(style <> 'referral' AND referral_context IS NULL)",
            name="ck_message_draft_referral_context",
        ),
        CheckConstraint("jsonb_typeof(skills) = 'array'", name="ck_message_draft_skills"),
        CheckConstraint(
            "length(variant_content_fingerprint) = 64 AND "
            "length(generation_identity) = 64 AND "
            "length(content_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_message_draft_hashes",
        ),
        CheckConstraint(
            "(company_snapshot_id IS NULL AND company_snapshot_version IS NULL AND "
            "company_snapshot_hash IS NULL AND company_freshness IS NULL AND "
            "company_industry IS NULL) OR "
            "(company_snapshot_id IS NOT NULL AND company_snapshot_version >= 1 AND "
            "length(company_snapshot_hash) = 64 AND company_freshness IS NOT NULL)",
            name="ck_message_draft_company_identity",
        ),
        ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_message_draft_variant_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["candidate_profile_id", "candidate_profile_version", "owner_id"],
            [
                "candidate_profile_versions.profile_id",
                "candidate_profile_versions.version",
                "candidate_profile_versions.owner_id",
            ],
            name="fk_message_draft_profile_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_message_draft_resume_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["job_posting_id", "job_posting_version", "owner_id"],
            ["job_postings.id", "job_postings.version", "job_postings.owner_id"],
            name="fk_message_draft_job_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_snapshot_id", "company_snapshot_version", "owner_id"],
            [
                "company_snapshots.snapshot_id",
                "company_snapshots.version",
                "company_snapshots.owner_id",
            ],
            name="fk_message_draft_company_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "previous_version", "owner_id"],
            ["message_drafts.id", "message_drafts.version", "message_drafts.owner_id"],
            name="fk_message_draft_previous_version",
            ondelete="RESTRICT",
        ),
    )

    record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    application_decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_variant_version: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    candidate_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_posting_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    job_posting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    company_snapshot_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    company_snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_freshness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_type: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationRecordRow(Base):
    __tablename__ = "application_records"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_application_record_identity"),
        UniqueConstraint(
            "owner_id", "application_decision_id", name="uq_application_record_owner_decision"
        ),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_application_record_owner_key"),
        CheckConstraint("version >= 1", name="ck_application_record_version"),
        CheckConstraint(
            "status IN ('planned', 'applied', 'interviewing', 'offer_received', "
            "'rejected', 'withdrawn')",
            name="ck_application_record_status",
        ),
        CheckConstraint("created_by = owner_id", name="ck_application_record_creator_owner"),
        CheckConstraint(
            "length(variant_content_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_application_record_hashes",
        ),
        CheckConstraint(
            "(resume_pdf_id IS NULL AND resume_pdf_version IS NULL AND artifact_id IS NULL AND "
            "artifact_version IS NULL AND artifact_sha256 IS NULL) OR "
            "(resume_pdf_id IS NOT NULL AND resume_pdf_version >= 1 AND artifact_id IS NOT NULL "
            "AND artifact_version >= 1 AND length(artifact_sha256) = 64)",
            name="ck_application_record_pdf_reference",
        ),
        CheckConstraint(
            "(message_draft_id IS NULL AND message_draft_version IS NULL AND "
            "message_content_fingerprint IS NULL) OR (message_draft_id IS NOT NULL AND "
            "message_draft_version >= 1 AND length(message_content_fingerprint) = 64)",
            name="ck_application_record_draft_reference",
        ),
        ForeignKeyConstraint(
            ["application_decision_id", "decision_case_id", "owner_id"],
            [
                "application_decisions.id",
                "application_decisions.decision_case_id",
                "application_decisions.owner_id",
            ],
            name="fk_application_record_apply_decision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_application_record_variant_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resume_pdf_id", "resume_pdf_version", "owner_id"],
            ["resume_pdfs.id", "resume_pdfs.version", "resume_pdfs.owner_id"],
            name="fk_application_record_pdf_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_application_record_artifact_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["message_draft_id", "message_draft_version", "owner_id"],
            ["message_drafts.id", "message_drafts.version", "message_drafts.owner_id"],
            name="fk_application_record_draft_owner",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    application_decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_variant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resume_variant_version: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    resume_pdf_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resume_pdf_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_draft_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    message_draft_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    application_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    application_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ApplicationRecordTransitionRow(Base):
    __tablename__ = "application_record_transitions"
    __table_args__ = (
        UniqueConstraint(
            "application_record_id",
            "record_version",
            name="uq_application_transition_record_version",
        ),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_application_transition_owner_key"),
        CheckConstraint("record_version >= 2", name="ck_application_transition_version"),
        CheckConstraint(
            "from_status IN ('planned', 'applied', 'interviewing', 'offer_received', "
            "'rejected', 'withdrawn') AND to_status IN ('planned', 'applied', 'interviewing', "
            "'offer_received', 'rejected', 'withdrawn') AND from_status <> to_status",
            name="ck_application_transition_statuses",
        ),
        CheckConstraint("source = 'user_confirmation'", name="ck_application_transition_source"),
        CheckConstraint("actor_id = owner_id", name="ck_application_transition_actor_owner"),
        CheckConstraint(
            "to_status <> 'applied' OR channel IS NOT NULL",
            name="ck_application_transition_applied_channel",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_application_transition_fingerprint"
        ),
        ForeignKeyConstraint(
            ["application_record_id", "owner_id"],
            ["application_records.id", "application_records.owner_id"],
            name="fk_application_transition_record_owner",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class SqlAlchemyTemplateDefinitionRepository:
    @staticmethod
    def _to_domain(record: TemplateDefinitionRecord) -> TemplateDefinition:
        value = record.definition
        section_order = cast(list[object], value["section_order"])
        allowed_fields = cast(list[object], value["allowed_fields"])
        required_fields = cast(list[object], value["required_fields"])
        template = TemplateDefinition.create(
            template_id=record.template_id,
            version=record.version,
            name=record.name,
            page_size=TemplatePageSize(str(value["page_size"])),
            density=TemplateDensity(str(value["density"])),
            accent=TemplateAccent(str(value["accent"])),
            section_order=tuple(str(item) for item in section_order),
            allowed_fields=tuple(str(item) for item in allowed_fields),
            required_fields=tuple(str(item) for item in required_fields),
            published_at=_as_utc(record.published_at),
        )
        if template.definition_hash != record.definition_hash:
            raise InfrastructureError(
                "Template definition hash is invalid",
                error_code=ErrorCode.TEMPLATE_DEFINITION_INVALID,
            )
        return template

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[TemplateDefinition]:
        records = await self.session.scalars(
            select(TemplateDefinitionRecord).order_by(
                TemplateDefinitionRecord.name, TemplateDefinitionRecord.version.desc()
            )
        )
        return [self._to_domain(record) for record in records]

    async def get_by_identity(self, template_id: UUID, version: int) -> TemplateDefinition | None:
        record = await self.session.scalar(
            select(TemplateDefinitionRecord).where(
                TemplateDefinitionRecord.template_id == template_id,
                TemplateDefinitionRecord.version == version,
            )
        )
        return None if record is None else self._to_domain(record)


class SqlAlchemyResumeVariantRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: ResumeVariantRecord) -> ResumeVariant:
        return ResumeVariant.restore(
            variant_id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            application_decision_id=record.application_decision_id,
            decision_case_id=record.decision_case_id,
            job_posting_id=record.job_posting_id,
            job_posting_version=record.job_posting_version,
            job_requirement_snapshot_id=record.job_requirement_snapshot_id,
            job_requirement_snapshot_version=record.job_requirement_snapshot_version,
            resume_version_id=record.resume_version_id,
            resume_version=record.resume_version,
            template_id=record.template_id,
            template_version=record.template_version,
            title=record.title,
            blocks=tuple(VariantBlock.create(**item) for item in record.blocks),
            generator_version=record.generator_version,
            content_fingerprint=record.content_fingerprint,
            idempotency_key=record.idempotency_key,
            created_at=_as_utc(record.variant_created_at),
        )

    async def add(self, variant: ResumeVariant) -> ResumeVariant:
        if variant.owner_id != self.owner_id:
            raise InfrastructureError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        record = ResumeVariantRecord(
            id=variant.id,
            owner_id=variant.owner_id,
            version=variant.version,
            application_decision_id=variant.application_decision_id,
            decision_case_id=variant.decision_case_id,
            job_posting_id=variant.job_posting_id,
            job_posting_version=variant.job_posting_version,
            job_requirement_snapshot_id=variant.job_requirement_snapshot_id,
            job_requirement_snapshot_version=variant.job_requirement_snapshot_version,
            resume_version_id=variant.resume_version_id,
            resume_version=variant.resume_version,
            template_id=variant.template_id,
            template_version=variant.template_version,
            title=variant.title,
            blocks=[
                {"source_path": item.source_path, "label": item.label, "value": item.value}
                for item in variant.blocks
            ],
            generator_version=variant.generator_version,
            content_fingerprint=variant.content_fingerprint,
            idempotency_key=variant.idempotency_key,
            variant_created_at=variant.created_at,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Resume variant already exists", error_code=ErrorCode.RESUME_VARIANT_KEY_TAKEN
            ) from exc
        return self._to_domain(record)

    async def get_by_id(self, variant_id: UUID) -> ResumeVariant | None:
        record = await self.session.scalar(
            select(ResumeVariantRecord).where(
                ResumeVariantRecord.id == variant_id,
                ResumeVariantRecord.owner_id == self.owner_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_idempotency_key(self, key: str) -> ResumeVariant | None:
        record = await self.session.scalar(
            select(ResumeVariantRecord).where(
                ResumeVariantRecord.owner_id == self.owner_id,
                ResumeVariantRecord.idempotency_key == key,
            )
        )
        return None if record is None else self._to_domain(record)

    async def list(self, *, offset: int, limit: int) -> list[ResumeVariant]:
        records = await self.session.scalars(
            select(ResumeVariantRecord)
            .where(ResumeVariantRecord.owner_id == self.owner_id)
            .order_by(ResumeVariantRecord.variant_created_at.desc(), ResumeVariantRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [self._to_domain(record) for record in records]

    async def count(self) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(ResumeVariantRecord)
            .where(ResumeVariantRecord.owner_id == self.owner_id)
        )
        return int(value or 0)

    async def commit(self) -> None:
        await self.session.commit()


class SqlAlchemyMessageDraftRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: MessageDraftRecord) -> MessageDraft:
        return MessageDraft.restore(
            draft_id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            source=MessageDraftSource(
                application_decision_id=record.application_decision_id,
                report_id=record.report_id,
                report_version=record.report_version,
                decision_case_id=record.decision_case_id,
                resume_variant_id=record.resume_variant_id,
                resume_variant_version=record.resume_variant_version,
                variant_content_fingerprint=record.variant_content_fingerprint,
                candidate_profile_id=record.candidate_profile_id,
                candidate_profile_version=record.candidate_profile_version,
                resume_version_id=record.resume_version_id,
                resume_version=record.resume_version,
                job_posting_id=record.job_posting_id,
                job_posting_version=record.job_posting_version,
                display_name=record.display_name,
                company_name=record.company_name,
                job_title=record.job_title,
                skills=tuple(record.skills),
                company_snapshot_id=record.company_snapshot_id,
                company_snapshot_version=record.company_snapshot_version,
                company_snapshot_hash=record.company_snapshot_hash,
                company_freshness=record.company_freshness,
                company_industry=record.company_industry,
            ),
            style=MessageDraftStyle(record.style),
            user_note=record.user_note,
            referral_context=record.referral_context,
            generator_version=record.generator_version,
            template_version=record.template_version,
            generation_identity=record.generation_identity,
            text=record.text,
            content_fingerprint=record.content_fingerprint,
            revision_type=MessageDraftRevisionType(record.revision_type),
            previous_version=record.previous_version,
            idempotency_key=record.idempotency_key,
            request_fingerprint=record.request_fingerprint,
            created_at=_as_utc(record.draft_created_at),
        )

    async def add(self, draft: MessageDraft) -> MessageDraft:
        if draft.owner_id != self.owner_id:
            raise InfrastructureError(
                "Message draft not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        record = MessageDraftRecord(record_id=uuid4(), **_message_draft_values(draft))
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Message draft already exists", error_code=ErrorCode.MESSAGE_DRAFT_CONFLICT
            ) from exc
        return self._to_domain(record)

    async def get_latest(self, draft_id: UUID) -> MessageDraft | None:
        record = await self.session.scalar(
            select(MessageDraftRecord)
            .where(
                MessageDraftRecord.id == draft_id,
                MessageDraftRecord.owner_id == self.owner_id,
            )
            .order_by(MessageDraftRecord.version.desc())
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def get_version(self, draft_id: UUID, version: int) -> MessageDraft | None:
        record = await self.session.scalar(
            select(MessageDraftRecord).where(
                MessageDraftRecord.id == draft_id,
                MessageDraftRecord.version == version,
                MessageDraftRecord.owner_id == self.owner_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_idempotency_key(self, key: str) -> MessageDraft | None:
        record = await self.session.scalar(
            select(MessageDraftRecord).where(
                MessageDraftRecord.owner_id == self.owner_id,
                MessageDraftRecord.idempotency_key == key,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_generation_identity(self, identity: str) -> MessageDraft | None:
        record = await self.session.scalar(
            select(MessageDraftRecord).where(
                MessageDraftRecord.owner_id == self.owner_id,
                MessageDraftRecord.generation_identity == identity,
                MessageDraftRecord.version == 1,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_latest_by_variant(self, variant_id: UUID) -> MessageDraft | None:
        record = await self.session.scalar(
            select(MessageDraftRecord)
            .where(
                MessageDraftRecord.owner_id == self.owner_id,
                MessageDraftRecord.resume_variant_id == variant_id,
            )
            .order_by(
                MessageDraftRecord.draft_created_at.desc(),
                MessageDraftRecord.version.desc(),
            )
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def list(self, *, offset: int, limit: int) -> list[MessageDraft]:
        latest = (
            select(
                MessageDraftRecord.id.label("draft_id"),
                func.max(MessageDraftRecord.version).label("latest_version"),
            )
            .where(MessageDraftRecord.owner_id == self.owner_id)
            .group_by(MessageDraftRecord.id)
            .subquery()
        )
        records = await self.session.scalars(
            select(MessageDraftRecord)
            .join(
                latest,
                and_(
                    MessageDraftRecord.id == latest.c.draft_id,
                    MessageDraftRecord.version == latest.c.latest_version,
                ),
            )
            .where(MessageDraftRecord.owner_id == self.owner_id)
            .order_by(MessageDraftRecord.draft_created_at.desc(), MessageDraftRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [self._to_domain(record) for record in records]

    async def list_versions(self, draft_id: UUID) -> Sequence[MessageDraft]:
        records = await self.session.scalars(
            select(MessageDraftRecord)
            .where(
                MessageDraftRecord.id == draft_id,
                MessageDraftRecord.owner_id == self.owner_id,
            )
            .order_by(MessageDraftRecord.version.desc())
        )
        return [self._to_domain(record) for record in records]

    async def count(self) -> int:
        value = await self.session.scalar(
            select(func.count(func.distinct(MessageDraftRecord.id))).where(
                MessageDraftRecord.owner_id == self.owner_id
            )
        )
        return int(value or 0)

    async def commit(self) -> None:
        await self.session.commit()


class SqlAlchemyApplicationRecordRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(row: ApplicationRecordRow) -> ApplicationRecord:
        return ApplicationRecord.restore(
            record_id=row.id,
            owner_id=row.owner_id,
            created_by=row.created_by,
            version=row.version,
            status=ApplicationRecordStatus(row.status),
            application_decision_id=row.application_decision_id,
            decision_case_id=row.decision_case_id,
            resume_variant_id=row.resume_variant_id,
            resume_variant_version=row.resume_variant_version,
            variant_content_fingerprint=row.variant_content_fingerprint,
            resume_pdf_id=row.resume_pdf_id,
            resume_pdf_version=row.resume_pdf_version,
            artifact_id=row.artifact_id,
            artifact_version=row.artifact_version,
            artifact_sha256=row.artifact_sha256,
            message_draft_id=row.message_draft_id,
            message_draft_version=row.message_draft_version,
            message_content_fingerprint=row.message_content_fingerprint,
            idempotency_key=row.idempotency_key,
            request_fingerprint=row.request_fingerprint,
            created_at=_as_utc(row.application_created_at),
            updated_at=_as_utc(row.application_updated_at),
        )

    async def add(self, record: ApplicationRecord) -> ApplicationRecord:
        self._check_owner(record)
        row = ApplicationRecordRow(**_application_record_values(record))
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            error_code = (
                ErrorCode.APPLICATION_RECORD_KEY_TAKEN
                if constraint == "uq_application_record_owner_key"
                else ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT
            )
            raise InfrastructureError(
                "Application record already exists", error_code=error_code
            ) from exc
        return self._to_domain(row)

    async def update(
        self, record: ApplicationRecord, *, expected_version: int
    ) -> ApplicationRecord:
        self._check_owner(record)
        row = await self.session.scalar(
            select(ApplicationRecordRow)
            .where(
                ApplicationRecordRow.id == record.id,
                ApplicationRecordRow.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if row is None:
            raise InfrastructureError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        if row.version != expected_version:
            raise InfrastructureError(
                "Application record version changed",
                error_code=ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT,
            )
        for name, value in _application_record_values(record).items():
            setattr(row, name, value)
        await self.session.flush()
        return self._to_domain(row)

    async def get_by_id(self, record_id: UUID) -> ApplicationRecord | None:
        row = await self.session.scalar(
            select(ApplicationRecordRow).where(
                ApplicationRecordRow.id == record_id,
                ApplicationRecordRow.owner_id == self.owner_id,
            )
        )
        return None if row is None else self._to_domain(row)

    async def get_by_decision_id(self, decision_id: UUID) -> ApplicationRecord | None:
        row = await self.session.scalar(
            select(ApplicationRecordRow).where(
                ApplicationRecordRow.application_decision_id == decision_id,
                ApplicationRecordRow.owner_id == self.owner_id,
            )
        )
        return None if row is None else self._to_domain(row)

    async def get_by_idempotency_key(self, key: str) -> ApplicationRecord | None:
        row = await self.session.scalar(
            select(ApplicationRecordRow).where(
                ApplicationRecordRow.idempotency_key == key,
                ApplicationRecordRow.owner_id == self.owner_id,
            )
        )
        return None if row is None else self._to_domain(row)

    async def list(self, *, offset: int, limit: int) -> list[ApplicationRecord]:
        rows = await self.session.scalars(
            select(ApplicationRecordRow)
            .where(ApplicationRecordRow.owner_id == self.owner_id)
            .order_by(
                ApplicationRecordRow.application_updated_at.desc(),
                ApplicationRecordRow.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return [self._to_domain(row) for row in rows]

    async def count(self) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(ApplicationRecordRow)
            .where(ApplicationRecordRow.owner_id == self.owner_id)
        )
        return int(value or 0)

    def _check_owner(self, record: ApplicationRecord) -> None:
        if record.owner_id != self.owner_id:
            raise InfrastructureError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )


class SqlAlchemyApplicationRecordTransitionRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(row: ApplicationRecordTransitionRow) -> ApplicationRecordTransition:
        return ApplicationRecordTransition.restore(
            transition_id=row.id,
            owner_id=row.owner_id,
            application_record_id=row.application_record_id,
            record_version=row.record_version,
            actor_id=row.actor_id,
            from_status=ApplicationRecordStatus(row.from_status),
            to_status=ApplicationRecordStatus(row.to_status),
            source=ApplicationTransitionSource(row.source),
            channel=row.channel,
            note=row.note,
            occurred_at=_as_utc(row.occurred_at),
            recorded_at=_as_utc(row.recorded_at),
            idempotency_key=row.idempotency_key,
            request_fingerprint=row.request_fingerprint,
        )

    async def add(self, transition: ApplicationRecordTransition) -> ApplicationRecordTransition:
        if transition.owner_id != self.owner_id:
            raise InfrastructureError(
                "Application transition not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        row = ApplicationRecordTransitionRow(**_application_transition_values(transition))
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            error_code = (
                ErrorCode.APPLICATION_RECORD_KEY_TAKEN
                if constraint == "uq_application_transition_owner_key"
                else ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT
            )
            raise InfrastructureError(
                "Application transition already exists", error_code=error_code
            ) from exc
        return self._to_domain(row)

    async def get_by_idempotency_key(self, key: str) -> ApplicationRecordTransition | None:
        row = await self.session.scalar(
            select(ApplicationRecordTransitionRow).where(
                ApplicationRecordTransitionRow.owner_id == self.owner_id,
                ApplicationRecordTransitionRow.idempotency_key == key,
            )
        )
        return None if row is None else self._to_domain(row)

    async def list_for_record(self, record_id: UUID) -> list[ApplicationRecordTransition]:
        rows = await self.session.scalars(
            select(ApplicationRecordTransitionRow)
            .where(
                ApplicationRecordTransitionRow.owner_id == self.owner_id,
                ApplicationRecordTransitionRow.application_record_id == record_id,
            )
            .order_by(ApplicationRecordTransitionRow.record_version)
        )
        return [self._to_domain(row) for row in rows]


class SqlAlchemyResumePdfRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _to_domain(record: ResumePdfRecord) -> ResumePdf:
        return ResumePdf.restore(
            pdf_id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            resume_variant_id=record.resume_variant_id,
            resume_variant_version=record.resume_variant_version,
            template_id=record.template_id,
            template_version=record.template_version,
            template_definition_hash=record.template_definition_hash,
            variant_content_fingerprint=record.variant_content_fingerprint,
            renderer_version=record.renderer_version,
            font_set_version=record.font_set_version,
            locale=record.locale,
            timezone_name=record.timezone,
            generation_identity=record.generation_identity,
            status=ResumePdfStatus(record.status),
            artifact_id=record.artifact_id,
            artifact_version=record.artifact_version,
            artifact_sha256=record.artifact_sha256,
            artifact_size_bytes=record.artifact_size_bytes,
            created_at=_as_utc(record.pdf_created_at),
            updated_at=_as_utc(record.pdf_updated_at),
        )

    async def add(self, pdf: ResumePdf) -> ResumePdf:
        self._check_owner(pdf)
        record = ResumePdfRecord(**_resume_pdf_values(pdf))
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Resume PDF already exists", error_code=ErrorCode.RESUME_PDF_CONFLICT
            ) from exc
        return self._to_domain(record)

    async def update(self, pdf: ResumePdf) -> ResumePdf:
        self._check_owner(pdf)
        record = await self.session.scalar(
            select(ResumePdfRecord)
            .where(
                ResumePdfRecord.id == pdf.id,
                ResumePdfRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if record is None:
            raise InfrastructureError("Resume PDF not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        for name, value in _resume_pdf_values(pdf).items():
            setattr(record, name, value)
        await self.session.flush()
        return pdf

    async def get_by_id(self, pdf_id: UUID) -> ResumePdf | None:
        record = await self.session.scalar(
            select(ResumePdfRecord).where(
                ResumePdfRecord.id == pdf_id,
                ResumePdfRecord.owner_id == self.owner_id,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_by_generation_identity(self, identity: str) -> ResumePdf | None:
        record = await self.session.scalar(
            select(ResumePdfRecord).where(
                ResumePdfRecord.owner_id == self.owner_id,
                ResumePdfRecord.generation_identity == identity,
            )
        )
        return None if record is None else self._to_domain(record)

    async def get_latest_by_variant(self, variant_id: UUID) -> ResumePdf | None:
        record = await self.session.scalar(
            select(ResumePdfRecord)
            .where(
                ResumePdfRecord.owner_id == self.owner_id,
                ResumePdfRecord.resume_variant_id == variant_id,
            )
            .order_by(ResumePdfRecord.pdf_created_at.desc(), ResumePdfRecord.id.desc())
            .limit(1)
        )
        return None if record is None else self._to_domain(record)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    def _check_owner(self, pdf: ResumePdf) -> None:
        if pdf.owner_id != self.owner_id:
            raise InfrastructureError("Resume PDF not found", error_code=ErrorCode.ENTITY_NOT_FOUND)


def _resume_pdf_values(value: ResumePdf) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "version": value.version,
        "resume_variant_id": value.resume_variant_id,
        "resume_variant_version": value.resume_variant_version,
        "template_id": value.template_id,
        "template_version": value.template_version,
        "template_definition_hash": value.template_definition_hash,
        "variant_content_fingerprint": value.variant_content_fingerprint,
        "renderer_version": value.renderer_version,
        "font_set_version": value.font_set_version,
        "locale": value.locale,
        "timezone": value.timezone,
        "generation_identity": value.generation_identity,
        "status": value.status.value,
        "artifact_id": value.artifact_id,
        "artifact_version": value.artifact_version,
        "artifact_sha256": value.artifact_sha256,
        "artifact_size_bytes": value.artifact_size_bytes,
        "pdf_created_at": value.created_at,
        "pdf_updated_at": value.updated_at,
    }


def _application_record_values(value: ApplicationRecord) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "created_by": value.created_by,
        "version": value.version,
        "status": value.status.value,
        "application_decision_id": value.application_decision_id,
        "decision_case_id": value.decision_case_id,
        "resume_variant_id": value.resume_variant_id,
        "resume_variant_version": value.resume_variant_version,
        "variant_content_fingerprint": value.variant_content_fingerprint,
        "resume_pdf_id": value.resume_pdf_id,
        "resume_pdf_version": value.resume_pdf_version,
        "artifact_id": value.artifact_id,
        "artifact_version": value.artifact_version,
        "artifact_sha256": value.artifact_sha256,
        "message_draft_id": value.message_draft_id,
        "message_draft_version": value.message_draft_version,
        "message_content_fingerprint": value.message_content_fingerprint,
        "idempotency_key": value.idempotency_key,
        "request_fingerprint": value.request_fingerprint,
        "application_created_at": value.created_at,
        "application_updated_at": value.updated_at,
    }


def _application_transition_values(
    value: ApplicationRecordTransition,
) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "application_record_id": value.application_record_id,
        "record_version": value.record_version,
        "actor_id": value.actor_id,
        "from_status": value.from_status.value,
        "to_status": value.to_status.value,
        "source": value.source.value,
        "channel": value.channel,
        "note": value.note,
        "occurred_at": value.occurred_at,
        "recorded_at": value.recorded_at,
        "idempotency_key": value.idempotency_key,
        "request_fingerprint": value.request_fingerprint,
    }


def _message_draft_values(value: MessageDraft) -> dict[str, object]:
    source = value.source
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "version": value.version,
        "application_decision_id": source.application_decision_id,
        "report_id": source.report_id,
        "report_version": source.report_version,
        "decision_case_id": source.decision_case_id,
        "resume_variant_id": source.resume_variant_id,
        "resume_variant_version": source.resume_variant_version,
        "variant_content_fingerprint": source.variant_content_fingerprint,
        "candidate_profile_id": source.candidate_profile_id,
        "candidate_profile_version": source.candidate_profile_version,
        "resume_version_id": source.resume_version_id,
        "resume_version": source.resume_version,
        "job_posting_id": source.job_posting_id,
        "job_posting_version": source.job_posting_version,
        "display_name": source.display_name,
        "company_name": source.company_name,
        "job_title": source.job_title,
        "skills": list(source.skills),
        "company_snapshot_id": source.company_snapshot_id,
        "company_snapshot_version": source.company_snapshot_version,
        "company_snapshot_hash": source.company_snapshot_hash,
        "company_freshness": source.company_freshness,
        "company_industry": source.company_industry,
        "style": value.style.value,
        "user_note": value.user_note,
        "referral_context": value.referral_context,
        "generator_version": value.generator_version,
        "template_version": value.template_version,
        "generation_identity": value.generation_identity,
        "text": value.text,
        "content_fingerprint": value.content_fingerprint,
        "revision_type": value.revision_type.value,
        "previous_version": value.previous_version,
        "idempotency_key": value.idempotency_key,
        "request_fingerprint": value.request_fingerprint,
        "draft_created_at": value.created_at,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
