"""Authenticated InterviewCase API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.followup import (
    CreateInterviewCaseCommand,
    InterviewCaseUseCases,
    InterviewPreparationUseCases,
    InterviewReviewUseCases,
    ListInterviewCasesQuery,
    UpdateInterviewCaseCommand,
)
from app.application.knowledge import ArtifactService, KnowledgeRagService
from app.apps.api.dependencies.career import get_resume_version_repository
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.decision import (
    get_decision_case_repository,
    get_decision_report_repository,
    get_job_fit_analysis_repository,
    get_model_port,
)
from app.apps.api.dependencies.followup import (
    get_application_record_repository,
    get_interview_case_repository,
    get_interview_preparation_repository,
    get_interview_review_repository,
    get_memory_candidate_repository,
)
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.knowledge import get_artifact_service, get_knowledge_rag_service
from app.apps.api.dependencies.opportunity import get_job_posting_repository
from app.apps.api.dependencies.transaction import get_transaction
from app.domain.followup import (
    InterviewCase,
    InterviewCaseSource,
    InterviewCaseStatus,
    InterviewMode,
    InterviewPreparation,
    InterviewReview,
    MemoryCandidate,
    MemoryCandidateKind,
    MemoryCandidateStatus,
    PreparationPriority,
)
from app.domain.identity import User
from app.ports.career import ResumeVersionRepository
from app.ports.decision import (
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.followup import (
    ApplicationRecordRepository,
    InterviewCaseRepository,
    InterviewReviewRepository,
    MemoryCandidateRepository,
)
from app.ports.governance import AuditEventRepository
from app.ports.interview_preparation import InterviewPreparationRepository
from app.ports.model import ModelPort
from app.ports.opportunity import JobPostingRepository
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


class PreparationCitationResponse(BaseModel):
    citation_id: UUID
    source_id: UUID
    source_version: int
    locator: str
    excerpt: str
    score: float
    url: str


class PreparationTopicResponse(BaseModel):
    topic_id: str
    title: str
    priority: PreparationPriority
    reason: str
    estimated_effort_minutes: int
    status: str
    suggestion: str
    citation_ids: list[UUID]


class InterviewPreparationResponse(BaseModel):
    id: UUID
    interview_case_id: UUID
    interview_case_version: int
    version: int
    generator_version: str
    prompt_version: str
    decision_case_id: UUID
    decision_report_id: UUID | None
    decision_report_version: int | None
    topics: list[PreparationTopicResponse]
    citations: list[PreparationCitationResponse]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: InterviewPreparation) -> "InterviewPreparationResponse":
        return cls(
            id=value.id,
            interview_case_id=value.interview_case_id,
            interview_case_version=value.interview_case_version,
            version=value.version,
            generator_version=value.generator_version,
            prompt_version=value.prompt_version,
            decision_case_id=value.decision_case_id,
            decision_report_id=value.decision_report_id,
            decision_report_version=value.decision_report_version,
            topics=[
                PreparationTopicResponse.model_validate(item, from_attributes=True)
                for item in value.topics
            ],
            citations=[
                PreparationCitationResponse(
                    citation_id=item.citation_id,
                    source_id=item.source_id,
                    source_version=item.source_version,
                    locator=item.locator,
                    excerpt=item.excerpt,
                    score=item.score,
                    url=f"/sources/{item.source_id}",
                )
                for item in value.citations
            ],
            created_at=value.created_at,
        )


class InterviewReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[str] = Field(min_length=1, max_length=50)
    answers: list[str] = Field(min_length=1, max_length=50)
    self_assessment: str = Field(min_length=1, max_length=8_000)
    blockers: list[str] = Field(default_factory=list, max_length=50)
    outcome: str = Field(min_length=1, max_length=8_000)


class InterviewReviewResponse(BaseModel):
    id: UUID
    interview_case_id: UUID
    interview_case_version: int
    version: int
    questions: list[str]
    answers: list[str]
    self_assessment: str
    blockers: list[str]
    outcome: str
    created_at: datetime
    candidates: list["MemoryCandidateResponse"]


class MemoryCandidateResponse(BaseModel):
    id: UUID
    review_id: UUID
    review_version: int
    kind: MemoryCandidateKind
    text: str
    reason: str
    confidence: float | None
    unknown: bool
    suggested_action: str
    status: MemoryCandidateStatus
    source_id: UUID | None
    source_version: int | None
    created_at: datetime
    confirmed_at: datetime | None
    rejected_at: datetime | None

    @classmethod
    def from_domain(cls, value: MemoryCandidate) -> "MemoryCandidateResponse":
        return cls(
            id=value.id,
            review_id=value.review_id,
            review_version=value.review_version,
            kind=value.kind,
            text=value.text,
            reason=value.reason,
            confidence=value.confidence,
            unknown=value.unknown,
            suggested_action=value.suggested_action,
            status=value.status,
            source_id=value.source_id,
            source_version=value.source_version,
            created_at=value.created_at,
            confirmed_at=value.confirmed_at,
            rejected_at=value.rejected_at,
        )


def _review_response(
    review: InterviewReview, candidates: list[MemoryCandidate]
) -> InterviewReviewResponse:
    return InterviewReviewResponse(
        id=review.id,
        interview_case_id=review.interview_case_id,
        interview_case_version=review.interview_case_version,
        version=review.version,
        questions=list(review.questions),
        answers=list(review.answers),
        self_assessment=review.self_assessment,
        blockers=list(review.blockers),
        outcome=review.outcome,
        created_at=review.created_at,
        candidates=[MemoryCandidateResponse.from_domain(item) for item in candidates],
    )


def _review_use_cases(
    reviews: InterviewReviewRepository,
    candidates: MemoryCandidateRepository,
    interviews: InterviewCaseRepository,
    model: ModelPort,
    artifacts: ArtifactService,
    rag: KnowledgeRagService,
    audits: AuditEventRepository,
) -> InterviewReviewUseCases:
    return InterviewReviewUseCases(reviews, candidates, interviews, model, artifacts, rag, audits)


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


def _preparation_use_cases(
    preparations: InterviewPreparationRepository,
    interviews: InterviewCaseRepository,
    applications: ApplicationRecordRepository,
    decision_cases: DecisionCaseRepository,
    reports: DecisionReportRepository,
    resumes: ResumeVersionRepository,
    jobs: JobPostingRepository,
    job_fit: JobFitAnalysisRepository,
    rag: KnowledgeRagService,
) -> InterviewPreparationUseCases:
    return InterviewPreparationUseCases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    )


@router.post(
    "/{interview_id}/preparation",
    response_model=InterviewPreparationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_interview_preparation(
    interview_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    preparations: InterviewPreparationRepository = Depends(get_interview_preparation_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    decision_cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    reports: DecisionReportRepository = Depends(get_decision_report_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    job_fit: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
) -> InterviewPreparationResponse:
    result = await _preparation_use_cases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    ).generate(user.id, interview_id)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return InterviewPreparationResponse.from_domain(result.preparation)


@router.get("/{interview_id}/preparation", response_model=InterviewPreparationResponse)
async def get_interview_preparation(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    preparations: InterviewPreparationRepository = Depends(get_interview_preparation_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    decision_cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    reports: DecisionReportRepository = Depends(get_decision_report_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    job_fit: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
) -> InterviewPreparationResponse:
    value = await _preparation_use_cases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    ).get_latest(user.id, interview_id)
    return InterviewPreparationResponse.from_domain(value)


@router.get(
    "/{interview_id}/preparation/versions", response_model=list[InterviewPreparationResponse]
)
async def list_interview_preparation_versions(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    preparations: InterviewPreparationRepository = Depends(get_interview_preparation_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    decision_cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    reports: DecisionReportRepository = Depends(get_decision_report_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    job_fit: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
) -> list[InterviewPreparationResponse]:
    values = await _preparation_use_cases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    ).list_versions(user.id, interview_id)
    return [InterviewPreparationResponse.from_domain(value) for value in values]


@router.get(
    "/{interview_id}/preparation/versions/{version}", response_model=InterviewPreparationResponse
)
async def get_interview_preparation_version(
    interview_id: UUID,
    version: Annotated[int, Path(ge=1)],
    user: User = Depends(get_current_user),
    preparations: InterviewPreparationRepository = Depends(get_interview_preparation_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    decision_cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    reports: DecisionReportRepository = Depends(get_decision_report_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    job_fit: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
) -> InterviewPreparationResponse:
    value = await _preparation_use_cases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    ).get_version(user.id, interview_id, version)
    return InterviewPreparationResponse.from_domain(value)


@router.post(
    "/{interview_id}/reviews",
    response_model=InterviewReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_review(
    interview_id: UUID,
    payload: InterviewReviewRequest,
    user: User = Depends(get_current_user),
    reviews: InterviewReviewRepository = Depends(get_interview_review_repository),
    candidates: MemoryCandidateRepository = Depends(get_memory_candidate_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    model: ModelPort = Depends(get_model_port),
    artifacts: ArtifactService = Depends(get_artifact_service),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
) -> InterviewReviewResponse:
    result = await _review_use_cases(
        reviews, candidates, interviews, model, artifacts, rag, audits
    ).create(
        user.id,
        interview_id,
        questions=tuple(payload.questions),
        answers=tuple(payload.answers),
        self_assessment=payload.self_assessment,
        blockers=tuple(payload.blockers),
        outcome=payload.outcome,
    )
    return _review_response(result.review, list(result.candidates))


@router.get("/{interview_id}/reviews", response_model=list[InterviewReviewResponse])
async def list_interview_reviews(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    reviews: InterviewReviewRepository = Depends(get_interview_review_repository),
    candidates: MemoryCandidateRepository = Depends(get_memory_candidate_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    model: ModelPort = Depends(get_model_port),
    artifacts: ArtifactService = Depends(get_artifact_service),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
) -> list[InterviewReviewResponse]:
    values = await _review_use_cases(
        reviews, candidates, interviews, model, artifacts, rag, audits
    ).versions(user.id, interview_id)
    return [_review_response(review, items) for review, items in values]


@router.post("/memory-candidates/{candidate_id}/confirm", response_model=MemoryCandidateResponse)
async def confirm_memory_candidate(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    reviews: InterviewReviewRepository = Depends(get_interview_review_repository),
    candidates: MemoryCandidateRepository = Depends(get_memory_candidate_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    model: ModelPort = Depends(get_model_port),
    artifacts: ArtifactService = Depends(get_artifact_service),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
) -> MemoryCandidateResponse:
    value = await _review_use_cases(
        reviews, candidates, interviews, model, artifacts, rag, audits
    ).confirm(user.id, candidate_id)
    return MemoryCandidateResponse.from_domain(value)


@router.post("/memory-candidates/{candidate_id}/reject", response_model=MemoryCandidateResponse)
async def reject_memory_candidate(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    reviews: InterviewReviewRepository = Depends(get_interview_review_repository),
    candidates: MemoryCandidateRepository = Depends(get_memory_candidate_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    model: ModelPort = Depends(get_model_port),
    artifacts: ArtifactService = Depends(get_artifact_service),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
) -> MemoryCandidateResponse:
    value = await _review_use_cases(
        reviews, candidates, interviews, model, artifacts, rag, audits
    ).reject(user.id, candidate_id)
    return MemoryCandidateResponse.from_domain(value)


@router.post("/memory-candidates/{candidate_id}/revoke", response_model=MemoryCandidateResponse)
async def revoke_memory_candidate(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    reviews: InterviewReviewRepository = Depends(get_interview_review_repository),
    candidates: MemoryCandidateRepository = Depends(get_memory_candidate_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    model: ModelPort = Depends(get_model_port),
    artifacts: ArtifactService = Depends(get_artifact_service),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    audits: AuditEventRepository = Depends(get_audit_event_repository),
) -> MemoryCandidateResponse:
    value = await _review_use_cases(
        reviews, candidates, interviews, model, artifacts, rag, audits
    ).revoke(user.id, candidate_id)
    return MemoryCandidateResponse.from_domain(value)
