"""Authenticated deterministic MessageDraft generation and revision API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.followup import (
    EditMessageDraftCommand,
    GenerateMessageDraftCommand,
    ListMessageDraftsQuery,
    MessageDraftUseCases,
)
from app.apps.api.dependencies import (
    get_application_decision_repository,
    get_company_assessment_repository,
    get_company_snapshot_repository,
    get_current_user,
    get_decision_case_repository,
    get_job_posting_repository,
    get_message_draft_repository,
    get_resume_variant_repository,
    get_resume_version_repository,
)
from app.domain.followup import MessageDraft, MessageDraftRevisionType, MessageDraftStyle
from app.domain.identity import User
from app.ports.career import ResumeVersionRepository
from app.ports.decision import CompanyAssessmentRepository, DecisionCaseRepository
from app.ports.followup import (
    ApplicationDecisionRepository,
    MessageDraftRepository,
    ResumeVariantRepository,
)
from app.ports.opportunity import CompanySnapshotRepository, JobPostingRepository

router = APIRouter(tags=["message-drafts"])


class GenerateMessageDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: MessageDraftStyle = MessageDraftStyle.PROFESSIONAL
    user_note: str | None = Field(default=None, max_length=1_000)
    referral_context: str | None = Field(default=None, max_length=1_000)


class EditMessageDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4_000)


class MessageDraftResponse(BaseModel):
    id: UUID
    version: int
    application_decision_id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    resume_variant_id: UUID
    resume_variant_version: int
    variant_content_fingerprint: str
    candidate_profile_id: UUID
    candidate_profile_version: int
    resume_version_id: UUID
    resume_version: int
    job_posting_id: UUID
    job_posting_version: int
    company_snapshot_id: UUID | None
    company_snapshot_version: int | None
    company_snapshot_hash: str | None
    company_freshness: str | None
    style: MessageDraftStyle
    user_note: str | None
    referral_context: str | None
    generator_version: str
    template_version: str
    generation_identity: str
    text: str
    content_fingerprint: str
    revision_type: MessageDraftRevisionType
    previous_version: int | None
    created_at: datetime

    @classmethod
    def from_domain(cls, value: MessageDraft) -> "MessageDraftResponse":
        source = value.source
        return cls(
            id=value.id,
            version=value.version,
            application_decision_id=source.application_decision_id,
            report_id=source.report_id,
            report_version=source.report_version,
            decision_case_id=source.decision_case_id,
            resume_variant_id=source.resume_variant_id,
            resume_variant_version=source.resume_variant_version,
            variant_content_fingerprint=source.variant_content_fingerprint,
            candidate_profile_id=source.candidate_profile_id,
            candidate_profile_version=source.candidate_profile_version,
            resume_version_id=source.resume_version_id,
            resume_version=source.resume_version,
            job_posting_id=source.job_posting_id,
            job_posting_version=source.job_posting_version,
            company_snapshot_id=source.company_snapshot_id,
            company_snapshot_version=source.company_snapshot_version,
            company_snapshot_hash=source.company_snapshot_hash,
            company_freshness=source.company_freshness,
            style=value.style,
            user_note=value.user_note,
            referral_context=value.referral_context,
            generator_version=value.generator_version,
            template_version=value.template_version,
            generation_identity=value.generation_identity,
            text=value.text,
            content_fingerprint=value.content_fingerprint,
            revision_type=value.revision_type,
            previous_version=value.previous_version,
            created_at=value.created_at,
        )


class MessageDraftListResponse(BaseModel):
    items: list[MessageDraftResponse]
    page: int
    page_size: int
    total: int


def _use_cases(
    drafts: MessageDraftRepository,
    variants: ResumeVariantRepository,
    decisions: ApplicationDecisionRepository,
    cases: DecisionCaseRepository,
    resumes: ResumeVersionRepository,
    jobs: JobPostingRepository,
    assessments: CompanyAssessmentRepository,
    companies: CompanySnapshotRepository,
) -> MessageDraftUseCases:
    return MessageDraftUseCases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    )


@router.post(
    "/resume-variants/{variant_id}/message-drafts",
    response_model=MessageDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_message_draft(
    variant_id: UUID,
    payload: GenerateMessageDraftRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftResponse:
    result = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).generate(
        GenerateMessageDraftCommand(
            owner_id=user.id,
            resume_variant_id=variant_id,
            style=payload.style,
            user_note=payload.user_note,
            referral_context=payload.referral_context,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return MessageDraftResponse.from_domain(result.draft)


@router.get(
    "/resume-variants/{variant_id}/message-draft",
    response_model=MessageDraftResponse,
)
async def get_latest_variant_message_draft(
    variant_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftResponse | Response:
    value = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).get_latest_for_variant(user.id, variant_id)
    if value is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return MessageDraftResponse.from_domain(value)


@router.get("/message-drafts", response_model=MessageDraftListResponse)
async def list_message_drafts(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftListResponse:
    result = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).list(ListMessageDraftsQuery(owner_id=user.id, page=page, page_size=page_size))
    return MessageDraftListResponse(
        items=[MessageDraftResponse.from_domain(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/message-drafts/{draft_id}", response_model=MessageDraftResponse)
async def get_message_draft(
    draft_id: UUID,
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftResponse:
    value = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).get(user.id, draft_id)
    return MessageDraftResponse.from_domain(value)


@router.get(
    "/message-drafts/{draft_id}/versions/{version}",
    response_model=MessageDraftResponse,
)
async def get_message_draft_version(
    draft_id: UUID,
    version: int,
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftResponse:
    value = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).get_version(user.id, draft_id, version)
    return MessageDraftResponse.from_domain(value)


@router.get(
    "/message-drafts/{draft_id}/versions",
    response_model=list[MessageDraftResponse],
)
async def list_message_draft_versions(
    draft_id: UUID,
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> list[MessageDraftResponse]:
    values = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).list_versions(user.id, draft_id)
    return [MessageDraftResponse.from_domain(item) for item in values]


@router.post(
    "/message-drafts/{draft_id}/revisions",
    response_model=MessageDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def edit_message_draft(
    draft_id: UUID,
    payload: EditMessageDraftRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    drafts: MessageDraftRepository = Depends(get_message_draft_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    assessments: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    companies: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> MessageDraftResponse:
    result = await _use_cases(
        drafts, variants, decisions, cases, resumes, jobs, assessments, companies
    ).edit(
        EditMessageDraftCommand(
            owner_id=user.id,
            draft_id=draft_id,
            base_version=payload.base_version,
            text=payload.text,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return MessageDraftResponse.from_domain(result.draft)
