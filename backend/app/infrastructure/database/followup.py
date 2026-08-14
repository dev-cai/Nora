"""Application & Follow-up ORM models and user-scoped repositories."""

from datetime import datetime, timezone
from typing import cast
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
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import InfrastructureError
from app.domain.followup import (
    ApplicationDecision,
    ApplicationDecisionStatus,
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

    async def commit(self) -> None:
        await self.session.commit()


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
                "Template definition hash is invalid", error_code="template_definition_invalid"
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
            raise InfrastructureError("Resume variant not found", error_code="entity_not_found")
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
                "Resume variant already exists", error_code="resume_variant_key_taken"
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
                "Resume PDF already exists", error_code="resume_pdf_conflict"
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
            raise InfrastructureError("Resume PDF not found", error_code="entity_not_found")
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
            raise InfrastructureError("Resume PDF not found", error_code="entity_not_found")


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
