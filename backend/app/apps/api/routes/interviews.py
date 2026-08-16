"""Authenticated InterviewCase API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.followup import (
    CreateInterviewCaseCommand,
    InterviewCaseUseCases,
    ListInterviewCasesQuery,
    UpdateInterviewCaseCommand,
)
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.followup import (
    get_application_record_repository,
    get_interview_case_repository,
)
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.transaction import get_transaction
from app.domain.followup import (
    InterviewCase,
    InterviewCaseSource,
    InterviewCaseStatus,
    InterviewMode,
)
from app.domain.identity import User
from app.ports.followup import ApplicationRecordRepository, InterviewCaseRepository
from app.ports.governance import AuditEventRepository
from app.ports.transaction import Transaction

application_router = APIRouter(prefix="/application-records", tags=["interviews"])
router = APIRouter(prefix="/interviews", tags=["interviews"])


class InterviewCaseFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    timezone: str = Field(min_length=1, max_length=100)
    mode: InterviewMode
    location: str | None = Field(default=None, max_length=500)
    meeting_url: str | None = Field(default=None, max_length=2_000)
    round_number: int = Field(ge=1, le=20)
    note: str | None = Field(default=None, max_length=2_000)
    status: InterviewCaseStatus = InterviewCaseStatus.SCHEDULED


class UpdateInterviewCaseRequest(InterviewCaseFields):
    base_version: int = Field(ge=1)


class InterviewCaseResponse(BaseModel):
    id: UUID
    application_record_id: UUID
    version: int
    actor_id: UUID
    starts_at: datetime
    timezone: str
    mode: InterviewMode
    location: str | None
    meeting_url: str | None
    round_number: int
    note: str | None
    source: InterviewCaseSource
    status: InterviewCaseStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: InterviewCase) -> "InterviewCaseResponse":
        return cls(
            id=value.id,
            application_record_id=value.application_record_id,
            version=value.version,
            actor_id=value.actor_id,
            starts_at=value.starts_at,
            timezone=value.timezone,
            mode=value.mode,
            location=value.location,
            meeting_url=value.meeting_url,
            round_number=value.round_number,
            note=value.note,
            source=value.source,
            status=value.status,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )


class InterviewCaseListResponse(BaseModel):
    items: list[InterviewCaseResponse]
    page: int
    page_size: int
    total: int


def _use_cases(
    interviews: InterviewCaseRepository,
    applications: ApplicationRecordRepository,
    audits: AuditEventRepository,
    transaction: Transaction,
) -> InterviewCaseUseCases:
    return InterviewCaseUseCases(interviews, applications, audits, transaction)


@application_router.post(
    "/{record_id}/interviews",
    response_model=InterviewCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview(
    record_id: UUID,
    payload: InterviewCaseFields,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> InterviewCaseResponse:
    result = await _use_cases(interviews, applications, audits, transaction).create(
        CreateInterviewCaseCommand(
            owner_id=user.id,
            actor_id=user.id,
            application_record_id=record_id,
            starts_at=payload.starts_at,
            timezone=payload.timezone,
            mode=payload.mode,
            location=payload.location,
            meeting_url=payload.meeting_url,
            round_number=payload.round_number,
            note=payload.note,
            status=payload.status,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return InterviewCaseResponse.from_domain(result.interview)


@router.get("", response_model=InterviewCaseListResponse)
async def list_interviews(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> InterviewCaseListResponse:
    result = await _use_cases(interviews, applications, audits, transaction).list_cases(
        ListInterviewCasesQuery(owner_id=user.id, page=page, page_size=page_size)
    )
    return InterviewCaseListResponse(
        items=[InterviewCaseResponse.from_domain(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{interview_id}", response_model=InterviewCaseResponse)
async def get_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> InterviewCaseResponse:
    value = await _use_cases(interviews, applications, audits, transaction).get(
        user.id, interview_id
    )
    return InterviewCaseResponse.from_domain(value)


@router.post(
    "/{interview_id}/versions",
    response_model=InterviewCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def update_interview(
    interview_id: UUID,
    payload: UpdateInterviewCaseRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> InterviewCaseResponse:
    result = await _use_cases(interviews, applications, audits, transaction).update(
        UpdateInterviewCaseCommand(
            owner_id=user.id,
            actor_id=user.id,
            interview_case_id=interview_id,
            base_version=payload.base_version,
            starts_at=payload.starts_at,
            timezone=payload.timezone,
            mode=payload.mode,
            location=payload.location,
            meeting_url=payload.meeting_url,
            round_number=payload.round_number,
            note=payload.note,
            status=payload.status,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return InterviewCaseResponse.from_domain(result.interview)


@router.get("/{interview_id}/versions", response_model=list[InterviewCaseResponse])
async def list_interview_versions(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> list[InterviewCaseResponse]:
    values = await _use_cases(interviews, applications, audits, transaction).list_versions(
        user.id, interview_id
    )
    return [InterviewCaseResponse.from_domain(value) for value in values]


@router.get("/{interview_id}/versions/{version}", response_model=InterviewCaseResponse)
async def get_interview_version(
    interview_id: UUID,
    version: Annotated[int, Path(ge=1)],
    user: User = Depends(get_current_user),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> InterviewCaseResponse:
    value = await _use_cases(interviews, applications, audits, transaction).get_version(
        user.id, interview_id, version
    )
    return InterviewCaseResponse.from_domain(value)
