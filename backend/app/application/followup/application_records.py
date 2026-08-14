"""Application use cases for user-confirmed manual application records."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.followup import (
    ApplicationDecisionStatus,
    ApplicationRecord,
    ApplicationRecordStatus,
    ApplicationRecordTransition,
    ResumePdfStatus,
    application_transition_request_fingerprint,
    normalize_application_idempotency_key,
)
from app.domain.governance import AuditAction, AuditEvent
from app.ports.followup import (
    ApplicationDecisionRepository,
    ApplicationRecordRepository,
    ApplicationRecordTransitionRepository,
    MessageDraftRepository,
    ResumePdfRepository,
    ResumeVariantRepository,
)
from app.ports.governance import AuditEventRepository
from app.ports.transaction import Transaction


@dataclass(frozen=True, slots=True)
class CreateApplicationRecordCommand:
    owner_id: UUID
    actor_id: UUID
    application_decision_id: UUID
    resume_variant_id: UUID
    resume_pdf_id: UUID | None
    message_draft_id: UUID | None
    message_draft_version: int | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TransitionApplicationRecordCommand:
    owner_id: UUID
    actor_id: UUID
    application_record_id: UUID
    base_version: int
    to_status: ApplicationRecordStatus
    occurred_at: datetime
    channel: str | None
    note: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ListApplicationRecordsQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ApplicationRecordResult:
    record: ApplicationRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class ApplicationRecordListResult:
    items: list[ApplicationRecord]
    page: int
    page_size: int
    total: int


class ApplicationRecordUseCases:
    def __init__(
        self,
        records: ApplicationRecordRepository,
        transitions: ApplicationRecordTransitionRepository,
        decisions: ApplicationDecisionRepository,
        variants: ResumeVariantRepository,
        pdfs: ResumePdfRepository,
        drafts: MessageDraftRepository,
        audits: AuditEventRepository,
        transaction: Transaction,
    ) -> None:
        self.records = records
        self.transitions = transitions
        self.decisions = decisions
        self.variants = variants
        self.pdfs = pdfs
        self.drafts = drafts
        self.audits = audits
        self.transaction = transaction

    async def create(self, command: CreateApplicationRecordCommand) -> ApplicationRecordResult:
        decision = await self.decisions.get_by_id(command.application_decision_id)
        if (
            decision is None
            or decision.owner_id != command.owner_id
            or decision.status is not ApplicationDecisionStatus.APPLY
        ):
            raise ApplicationError(
                "Apply decision not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        variant = await self.variants.get_by_id(command.resume_variant_id)
        if variant is None or variant.owner_id != command.owner_id:
            raise ApplicationError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        if (
            variant.application_decision_id != decision.id
            or variant.decision_case_id != decision.decision_case_id
        ):
            raise ApplicationError(
                "Resume variant does not belong to the apply decision",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )

        resume_pdf_id: UUID | None = None
        resume_pdf_version: int | None = None
        artifact_id: UUID | None = None
        artifact_version: int | None = None
        artifact_sha256: str | None = None
        if command.resume_pdf_id is not None:
            pdf = await self.pdfs.get_by_id(command.resume_pdf_id)
            if pdf is None or pdf.owner_id != command.owner_id:
                raise ApplicationError(
                    "Resume PDF not found", error_code=ErrorCode.ENTITY_NOT_FOUND
                )
            if (
                pdf.status is not ResumePdfStatus.AVAILABLE
                or pdf.resume_variant_id != variant.id
                or pdf.resume_variant_version != variant.version
                or pdf.variant_content_fingerprint != variant.content_fingerprint
            ):
                raise ApplicationError(
                    "Resume PDF is not an available artifact for this variant",
                    error_code=ErrorCode.INVALID_APPLICATION_RECORD,
                )
            resume_pdf_id = pdf.id
            resume_pdf_version = pdf.version
            artifact_id = pdf.artifact_id
            artifact_version = pdf.artifact_version
            artifact_sha256 = pdf.artifact_sha256

        message_draft_id: UUID | None = None
        message_draft_version: int | None = None
        message_content_fingerprint: str | None = None
        if (command.message_draft_id is None) != (command.message_draft_version is None):
            raise ApplicationError(
                "Message draft ID and version must be provided together",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        if command.message_draft_id is not None and command.message_draft_version is not None:
            draft = await self.drafts.get_version(
                command.message_draft_id, command.message_draft_version
            )
            if draft is None or draft.owner_id != command.owner_id:
                raise ApplicationError(
                    "Message draft version not found", error_code=ErrorCode.ENTITY_NOT_FOUND
                )
            if (
                draft.source.resume_variant_id != variant.id
                or draft.source.resume_variant_version != variant.version
                or draft.source.variant_content_fingerprint != variant.content_fingerprint
            ):
                raise ApplicationError(
                    "Message draft does not belong to this variant",
                    error_code=ErrorCode.INVALID_APPLICATION_RECORD,
                )
            message_draft_id = draft.id
            message_draft_version = draft.version
            message_content_fingerprint = draft.content_fingerprint

        candidate = ApplicationRecord.create(
            owner_id=command.owner_id,
            actor_id=command.actor_id,
            application_decision_id=decision.id,
            decision_case_id=decision.decision_case_id,
            resume_variant_id=variant.id,
            resume_variant_version=variant.version,
            variant_content_fingerprint=variant.content_fingerprint,
            idempotency_key=command.idempotency_key,
            resume_pdf_id=resume_pdf_id,
            resume_pdf_version=resume_pdf_version,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            artifact_sha256=artifact_sha256,
            message_draft_id=message_draft_id,
            message_draft_version=message_draft_version,
            message_content_fingerprint=message_content_fingerprint,
        )
        existing = await self.records.get_by_idempotency_key(candidate.idempotency_key)
        if existing is not None:
            return _resolve_record_replay(existing, candidate)
        existing = await self.records.get_by_decision_id(decision.id)
        if existing is not None:
            return _resolve_record_replay(existing, candidate)

        try:
            stored = await self.records.add(candidate)
            await self.audits.add(
                AuditEvent.create(
                    actor_id=command.actor_id,
                    action=AuditAction.CREATE,
                    target_type="application_record",
                    target_id=stored.id,
                    target_version=stored.version,
                    after_summary=_audit_summary(stored),
                    idempotency_key=stored.idempotency_key,
                )
            )
            await self.transaction.commit()
        except InfrastructureError as exc:
            await self.transaction.rollback()
            if exc.error_code not in {
                ErrorCode.APPLICATION_RECORD_KEY_TAKEN,
                ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT,
            }:
                raise
            winner = await self.records.get_by_idempotency_key(candidate.idempotency_key)
            if winner is None:
                winner = await self.records.get_by_decision_id(decision.id)
            if winner is not None:
                return _resolve_record_replay(winner, candidate)
            raise InfrastructureError(
                "Could not recover application record",
                error_code=ErrorCode.APPLICATION_RECORD_PERSISTENCE_FAILED,
            ) from exc
        except Exception:
            await self.transaction.rollback()
            raise
        return ApplicationRecordResult(record=stored, replayed=False)

    async def transition(
        self, command: TransitionApplicationRecordCommand
    ) -> ApplicationRecordResult:
        record = await self._get(command.owner_id, command.application_record_id)
        key = normalize_application_idempotency_key(command.idempotency_key)
        fingerprint = application_transition_request_fingerprint(
            application_record_id=record.id,
            base_version=command.base_version,
            to_status=command.to_status,
            occurred_at=command.occurred_at,
            channel=command.channel,
            note=command.note,
        )
        existing = await self.transitions.get_by_idempotency_key(key)
        if existing is not None:
            return await self._resolve_transition_replay(record.id, existing, fingerprint)
        if command.base_version != record.version:
            raise ApplicationError(
                "Application record version changed",
                error_code=ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT,
            )
        updated, event = record.transition(
            actor_id=command.actor_id,
            to_status=command.to_status,
            occurred_at=command.occurred_at,
            channel=command.channel,
            note=command.note,
            idempotency_key=key,
        )
        try:
            stored = await self.records.update(updated, expected_version=record.version)
            await self.transitions.add(event)
            await self.audits.add(
                AuditEvent.create(
                    actor_id=command.actor_id,
                    action=AuditAction.UPDATE,
                    target_type="application_record",
                    target_id=stored.id,
                    target_version=stored.version,
                    before_summary=_audit_summary(record),
                    after_summary=_audit_summary(stored),
                    idempotency_key=event.idempotency_key,
                )
            )
            await self.transaction.commit()
        except InfrastructureError as exc:
            await self.transaction.rollback()
            if exc.error_code not in {
                ErrorCode.APPLICATION_RECORD_KEY_TAKEN,
                ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT,
            }:
                raise
            winner = await self.transitions.get_by_idempotency_key(key)
            if winner is not None:
                return await self._resolve_transition_replay(record.id, winner, fingerprint)
            raise ApplicationError(
                "Application record version changed",
                error_code=ErrorCode.APPLICATION_RECORD_VERSION_CONFLICT,
            ) from exc
        except Exception:
            await self.transaction.rollback()
            raise
        return ApplicationRecordResult(record=stored, replayed=False)

    async def get(self, owner_id: UUID, record_id: UUID) -> ApplicationRecord:
        return await self._get(owner_id, record_id)

    async def list_records(self, query: ListApplicationRecordsQuery) -> ApplicationRecordListResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError("Pagination is invalid", error_code=ErrorCode.INVALID_PAGINATION)
        return ApplicationRecordListResult(
            items=await self.records.list(
                offset=(query.page - 1) * query.page_size, limit=query.page_size
            ),
            page=query.page,
            page_size=query.page_size,
            total=await self.records.count(),
        )

    async def list_transitions(
        self, owner_id: UUID, record_id: UUID
    ) -> list[ApplicationRecordTransition]:
        await self._get(owner_id, record_id)
        return await self.transitions.list_for_record(record_id)

    async def _get(self, owner_id: UUID, record_id: UUID) -> ApplicationRecord:
        record = await self.records.get_by_id(record_id)
        if record is None or record.owner_id != owner_id:
            raise ApplicationError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return record

    async def _resolve_transition_replay(
        self,
        record_id: UUID,
        existing: ApplicationRecordTransition,
        fingerprint: str,
    ) -> ApplicationRecordResult:
        if (
            existing.application_record_id != record_id
            or existing.request_fingerprint != fingerprint
        ):
            raise ApplicationError(
                "Idempotency key belongs to a different application transition",
                error_code=ErrorCode.APPLICATION_RECORD_KEY_TAKEN,
            )
        current = await self.records.get_by_id(record_id)
        if current is None:
            raise InfrastructureError(
                "Application transition has no record",
                error_code=ErrorCode.APPLICATION_RECORD_PERSISTENCE_FAILED,
            )
        return ApplicationRecordResult(record=current, replayed=True)


def _resolve_record_replay(
    existing: ApplicationRecord, candidate: ApplicationRecord
) -> ApplicationRecordResult:
    if not existing.has_same_request(candidate):
        raise ApplicationError(
            "Application record already exists with different materials",
            error_code=ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT,
        )
    return ApplicationRecordResult(record=existing, replayed=True)


def _audit_summary(record: ApplicationRecord) -> str:
    return (
        f"status={record.status.value};version={record.version};"
        f"decision={record.application_decision_id};variant={record.resume_variant_id}:"
        f"{record.resume_variant_version}"
    )
