"""Authenticated manual ApplicationRecord API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.followup import (
    ApplicationRecordUseCases,
    CreateApplicationRecordCommand,
    ListApplicationRecordsQuery,
    TransitionApplicationRecordCommand,
)
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.followup import (
    get_application_decision_repository,
    get_application_record_repository,
    get_application_record_transition_repository,
    get_message_draft_repository,
    get_resume_pdf_repository,
    get_resume_variant_repository,
)
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.transaction import get_transaction
from app.domain.followup import (
    ApplicationRecord,
    ApplicationRecordStatus,
    ApplicationRecordTransition,
    ApplicationTransitionSource,
)
from app.domain.identity import User
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

router = APIRouter(prefix="/application-records", tags=["application-records"])


class CreateApplicationRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_decision_id: UUID
    resume_variant_id: UUID
    resume_pdf_id: UUID | None = None
    message_draft_id: UUID | None = None
    message_draft_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_draft_identity(self) -> "CreateApplicationRecordRequest":
        if (self.message_draft_id is None) != (self.message_draft_version is None):
            raise ValueError("message_draft_id and message_draft_version must be provided together")
        return self


class TransitionApplicationRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int = Field(ge=1)
    to_status: ApplicationRecordStatus
    occurred_at: datetime
    channel: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1_000)


class ApplicationRecordResponse(BaseModel):
    id: UUID
    version: int
    status: ApplicationRecordStatus
    application_decision_id: UUID
    decision_case_id: UUID
    resume_variant_id: UUID
    resume_variant_version: int
    variant_content_fingerprint: str
    resume_pdf_id: UUID | None
    resume_pdf_version: int | None
    artifact_id: UUID | None
    artifact_version: int | None
    artifact_sha256: str | None
    message_draft_id: UUID | None
    message_draft_version: int | None
    message_content_fingerprint: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: ApplicationRecord) -> "ApplicationRecordResponse":
        return cls(
            id=value.id,
            version=value.version,
            status=value.status,
            application_decision_id=value.application_decision_id,
            decision_case_id=value.decision_case_id,
            resume_variant_id=value.resume_variant_id,
            resume_variant_version=value.resume_variant_version,
            variant_content_fingerprint=value.variant_content_fingerprint,
            resume_pdf_id=value.resume_pdf_id,
            resume_pdf_version=value.resume_pdf_version,
            artifact_id=value.artifact_id,
            artifact_version=value.artifact_version,
            artifact_sha256=value.artifact_sha256,
            message_draft_id=value.message_draft_id,
            message_draft_version=value.message_draft_version,
            message_content_fingerprint=value.message_content_fingerprint,
            created_by=value.created_by,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )


class ApplicationRecordTransitionResponse(BaseModel):
    id: UUID
    record_version: int
    actor_id: UUID
    from_status: ApplicationRecordStatus
    to_status: ApplicationRecordStatus
    source: ApplicationTransitionSource
    channel: str | None
    note: str | None
    occurred_at: datetime
    recorded_at: datetime

    @classmethod
    def from_domain(
        cls, value: ApplicationRecordTransition
    ) -> "ApplicationRecordTransitionResponse":
        return cls(
            id=value.id,
            record_version=value.record_version,
            actor_id=value.actor_id,
            from_status=value.from_status,
            to_status=value.to_status,
            source=value.source,
            channel=value.channel,
            note=value.note,
            occurred_at=value.occurred_at,
            recorded_at=value.recorded_at,
        )


class ApplicationRecordListResponse(BaseModel):
    items: list[ApplicationRecordResponse]
    page: int
    page_size: int
    total: int


def _use_cases(
    records: ApplicationRecordRepository,
    transitions: ApplicationRecordTransitionRepository,
    decisions: ApplicationDecisionRepository,
    variants: ResumeVariantRepository,
    pdfs: ResumePdfRepository,
    drafts: MessageDraftRepository,
    audits: AuditEventRepository,
    transaction: Transaction,
) -> ApplicationRecordUseCases:
    return ApplicationRecordUseCases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    )


@router.post("", response_model=ApplicationRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_application_record(
    payload: CreateApplicationRecordRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    records: ApplicationRecordRepository = Depends(get_application_record_repository),
    transitions: ApplicationRecordTransitionRepository = Depends(
        get_application_record_transition_repository
    ),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> ApplicationRecordResponse:
    result = await _use_cases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    ).create(
        CreateApplicationRecordCommand(
            owner_id=user.id,
            actor_id=user.id,
            application_decision_id=payload.application_decision_id,
            resume_variant_id=payload.resume_variant_id,
            resume_pdf_id=payload.resume_pdf_id,
            message_draft_id=payload.message_draft_id,
            message_draft_version=payload.message_draft_version,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ApplicationRecordResponse.from_domain(result.record)


@router.get("", response_model=ApplicationRecordListResponse)
async def list_application_records(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    records: ApplicationRecordRepository = Depends(get_application_record_repository),
    transitions: ApplicationRecordTransitionRepository = Depends(
        get_application_record_transition_repository
    ),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> ApplicationRecordListResponse:
    result = await _use_cases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    ).list_records(ListApplicationRecordsQuery(owner_id=user.id, page=page, page_size=page_size))
    return ApplicationRecordListResponse(
        items=[ApplicationRecordResponse.from_domain(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{record_id}", response_model=ApplicationRecordResponse)
async def get_application_record(
    record_id: UUID,
    user: User = Depends(get_current_user),
    records: ApplicationRecordRepository = Depends(get_application_record_repository),
    transitions: ApplicationRecordTransitionRepository = Depends(
        get_application_record_transition_repository
    ),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> ApplicationRecordResponse:
    value = await _use_cases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    ).get(user.id, record_id)
    return ApplicationRecordResponse.from_domain(value)


@router.get("/{record_id}/transitions", response_model=list[ApplicationRecordTransitionResponse])
async def list_application_record_transitions(
    record_id: UUID,
    user: User = Depends(get_current_user),
    records: ApplicationRecordRepository = Depends(get_application_record_repository),
    transitions: ApplicationRecordTransitionRepository = Depends(
        get_application_record_transition_repository
    ),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> list[ApplicationRecordTransitionResponse]:
    values = await _use_cases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    ).list_transitions(user.id, record_id)
    return [ApplicationRecordTransitionResponse.from_domain(value) for value in values]


@router.post(
    "/{record_id}/transitions",
    response_model=ApplicationRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transition_application_record(
    record_id: UUID,
    payload: TransitionApplicationRecordRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    records: ApplicationRecordRepository = Depends(get_application_record_repository),
    transitions: ApplicationRecordTransitionRepository = Depends(
        get_application_record_transition_repository
    ),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> ApplicationRecordResponse:
    result = await _use_cases(
        records, transitions, decisions, variants, pdfs, drafts, audits, transaction
    ).transition(
        TransitionApplicationRecordCommand(
            owner_id=user.id,
            actor_id=user.id,
            application_record_id=record_id,
            base_version=payload.base_version,
            to_status=payload.to_status,
            occurred_at=payload.occurred_at,
            channel=payload.channel,
            note=payload.note,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ApplicationRecordResponse.from_domain(result.record)
