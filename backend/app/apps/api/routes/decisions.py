"""Authenticated synchronous DecisionCase analysis and DecisionReport API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, Field, model_validator

from app.application.decision import (
    AnalyzeDecisionCaseQuery,
    AnalyzeDecisionCaseUseCase,
    CompanyAssessmentUseCases,
    CreateCompanyAssessmentCommand,
    CreateDecisionCaseCommand,
    CreateDecisionCaseUseCase,
    GenerateJobFitAnalysisCommand,
    GenerateJobFitAnalysisUseCase,
    GenerateStoredDecisionReportCommand,
    GenerateStoredDecisionReportUseCase,
    GetDecisionReportQuery,
    GetDecisionReportUseCase,
    ListDecisionReportsQuery,
    ListDecisionReportsUseCase,
    ReportCompanyAssessment,
)
from app.application.followup import (
    CreateApplicationDecisionCommand,
    CreateApplicationDecisionUseCase,
    GetApplicationDecisionQuery,
    GetApplicationDecisionUseCase,
)
from app.apps.api.dependencies.career import (
    get_candidate_profile_repository,
    get_resume_version_repository,
)
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.decision import (
    get_company_assessment_repository,
    get_decision_case_repository,
    get_decision_report_repository,
    get_job_fit_analysis_repository,
    get_model_port,
)
from app.apps.api.dependencies.followup import get_application_decision_repository
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.knowledge import (
    get_artifact_repository,
    get_source_document_repository,
)
from app.apps.api.dependencies.opportunity import (
    get_company_snapshot_repository,
    get_job_posting_repository,
    get_job_requirement_snapshot_repository,
)
from app.apps.api.dependencies.transaction import get_transaction
from app.apps.api.routes.companies import CompanySnapshotResponse
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.decision import (
    RULE_SET_VERSION,
    CompanyAssessmentStatus,
    DecisionCase,
    DecisionCaseStatus,
    DecisionReport,
    JobFitAnalysis,
    JobFitCitation,
    JobFitCitationSource,
    JobFitInsight,
    JobFitLevel,
    ReportCitation,
    ReportFact,
    ReportRecommendation,
    ReportRuleResult,
    ReportUnknown,
    RuleInputReference,
    RuleInputSource,
    RuleResult,
    RuleStatus,
)
from app.domain.followup import ApplicationDecision, ApplicationDecisionStatus
from app.domain.identity import User
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.followup import ApplicationDecisionRepository
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import ArtifactRepository, SourceDocumentRepository
from app.ports.model import ModelPort
from app.ports.opportunity import (
    CompanySnapshotRepository,
    JobPostingRepository,
    JobRequirementSnapshotRepository,
)
from app.ports.transaction import Transaction

REPORT_GENERATOR_VERSION = "m3-report-v1"

decision_router = APIRouter(prefix="/decisions", tags=["decisions"])
report_router = APIRouter(prefix="/reports", tags=["reports"])


class CreateDecisionCaseRequest(BaseModel):
    job_posting_id: UUID
    job_posting_version: int = Field(ge=1)
    job_requirement_snapshot_id: UUID
    job_requirement_snapshot_version: int = Field(ge=1)
    candidate_profile_id: UUID
    candidate_profile_version: int = Field(ge=1)
    resume_version_id: UUID
    resume_version: int = Field(ge=1)


class DecisionCaseResponse(BaseModel):
    id: UUID
    job_posting_id: UUID
    job_posting_version: int
    job_requirement_snapshot_id: UUID
    job_requirement_snapshot_version: int
    candidate_profile_id: UUID
    candidate_profile_version: int
    resume_version_id: UUID
    resume_version: int
    rule_set_version: str
    status: DecisionCaseStatus
    created_at: datetime
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_domain(cls, decision_case: DecisionCase) -> "DecisionCaseResponse":
        return cls.model_validate(decision_case, from_attributes=True)


class RuleInputReferenceResponse(BaseModel):
    source: RuleInputSource
    object_id: UUID
    version: int
    field_path: str

    @classmethod
    def from_domain(cls, reference: RuleInputReference) -> "RuleInputReferenceResponse":
        return cls.model_validate(reference, from_attributes=True)


class RuleResultResponse(BaseModel):
    rule_id: str
    rule_version: str
    status: RuleStatus
    input_references: list[RuleInputReferenceResponse]
    reason: str
    uncertainty: str | None
    suggestion: str | None

    @classmethod
    def from_domain(cls, result: RuleResult) -> "RuleResultResponse":
        return cls(
            rule_id=result.rule_id,
            rule_version=result.rule_version,
            status=result.status,
            input_references=[
                RuleInputReferenceResponse.from_domain(item) for item in result.input_references
            ],
            reason=result.reason,
            uncertainty=result.uncertainty,
            suggestion=result.suggestion,
        )


class DecisionAnalysisResponse(BaseModel):
    decision: DecisionCaseResponse
    rule_set_version: str
    rule_results: list[RuleResultResponse]


class ReportCitationResponse(BaseModel):
    citation_id: str
    source: RuleInputSource
    object_id: UUID
    version: int
    field_path: str

    @classmethod
    def from_domain(cls, item: ReportCitation) -> "ReportCitationResponse":
        return cls.model_validate(item, from_attributes=True)


class ReportFactResponse(BaseModel):
    fact_id: str
    label: str
    citation_ids: list[str]

    @classmethod
    def from_domain(cls, item: ReportFact) -> "ReportFactResponse":
        return cls(
            fact_id=item.fact_id,
            label=item.label,
            citation_ids=list(item.citation_ids),
        )


class ReportRuleResultResponse(BaseModel):
    rule_id: str
    rule_version: str
    status: RuleStatus
    reason: str
    citation_ids: list[str]

    @classmethod
    def from_domain(cls, item: ReportRuleResult) -> "ReportRuleResultResponse":
        return cls(
            rule_id=item.rule_id,
            rule_version=item.rule_version,
            status=item.status,
            reason=item.reason,
            citation_ids=list(item.citation_ids),
        )


class ReportUnknownResponse(BaseModel):
    unknown_id: str
    reason: str
    detail: str
    citation_ids: list[str]

    @classmethod
    def from_domain(cls, item: ReportUnknown) -> "ReportUnknownResponse":
        return cls(
            unknown_id=item.unknown_id,
            reason=item.reason,
            detail=item.detail,
            citation_ids=list(item.citation_ids),
        )


class ReportRecommendationResponse(BaseModel):
    recommendation_id: str
    action: str
    rationale: str
    source_rule_id: str

    @classmethod
    def from_domain(cls, item: ReportRecommendation) -> "ReportRecommendationResponse":
        return cls.model_validate(item, from_attributes=True)


class MatchSummaryResponse(BaseModel):
    match: int
    partial: int
    mismatch: int
    unknown: int


class CreateCompanyAssessmentRequest(BaseModel):
    company_snapshot_id: UUID
    company_snapshot_version: int = Field(ge=1)


class CompanyAssessmentResponse(BaseModel):
    id: UUID
    version: int
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    status: CompanyAssessmentStatus
    status_reason: str
    generator_version: str
    generation_identity: str
    snapshot: CompanySnapshotResponse
    created_at: datetime


def _company_assessment_use_cases(
    assessments: CompanyAssessmentRepository,
    reports: DecisionReportRepository,
    cases: DecisionCaseRepository,
    snapshots: CompanySnapshotRepository,
    sources: SourceDocumentRepository,
    artifacts: ArtifactRepository,
) -> CompanyAssessmentUseCases:
    return CompanyAssessmentUseCases(assessments, reports, cases, snapshots, sources, artifacts)


def _company_assessment_response(result: object) -> CompanyAssessmentResponse:
    assert isinstance(result, ReportCompanyAssessment)
    assessment = result.assessment
    return CompanyAssessmentResponse(
        id=assessment.id,
        version=assessment.version,
        report_id=assessment.report_id,
        report_version=assessment.report_version,
        decision_case_id=assessment.decision_case_id,
        status=assessment.status,
        status_reason=assessment.status_reason,
        generator_version=assessment.generator_version,
        generation_identity=assessment.generation_identity,
        snapshot=CompanySnapshotResponse.from_domain(result.snapshot),
        created_at=assessment.created_at,
    )


class DecisionReportResponse(BaseModel):
    id: UUID
    decision_case_id: UUID
    version: int
    rule_set_version: str
    generator_version: str
    summary: MatchSummaryResponse
    facts: list[ReportFactResponse]
    rule_results: list[ReportRuleResultResponse]
    unknowns: list[ReportUnknownResponse]
    recommendations: list[ReportRecommendationResponse]
    citations: list[ReportCitationResponse]
    satisfied_conditions: list[str]
    gaps: list[str]
    risks: list[str]
    next_steps: list[str]
    generated_at: datetime
    company_assessment: CompanyAssessmentResponse | None = None

    @classmethod
    def from_domain(
        cls,
        report: DecisionReport,
        company_assessment: CompanyAssessmentResponse | None = None,
    ) -> "DecisionReportResponse":
        return cls(
            id=report.id,
            decision_case_id=report.decision_case_id,
            version=report.version,
            rule_set_version=report.rule_set_version,
            generator_version=report.generator_version,
            summary=MatchSummaryResponse.model_validate(report.summary, from_attributes=True),
            facts=[ReportFactResponse.from_domain(item) for item in report.facts],
            rule_results=[
                ReportRuleResultResponse.from_domain(item) for item in report.rule_results
            ],
            unknowns=[ReportUnknownResponse.from_domain(item) for item in report.unknowns],
            recommendations=[
                ReportRecommendationResponse.from_domain(item) for item in report.recommendations
            ],
            citations=[ReportCitationResponse.from_domain(item) for item in report.citations],
            satisfied_conditions=list(report.satisfied_conditions),
            gaps=list(report.gaps),
            risks=list(report.risks),
            next_steps=list(report.next_steps),
            generated_at=report.generated_at,
            company_assessment=company_assessment,
        )


class DecisionReportListResponse(BaseModel):
    items: list[DecisionReportResponse]
    page: int
    page_size: int
    total: int


class JobFitCitationResponse(BaseModel):
    citation_id: str
    source: JobFitCitationSource
    object_id: UUID
    version: int
    field_path: str

    @classmethod
    def from_domain(cls, item: JobFitCitation) -> "JobFitCitationResponse":
        return cls.model_validate(item, from_attributes=True)


class JobFitInsightResponse(BaseModel):
    text: str
    citation_ids: list[str]

    @classmethod
    def from_domain(cls, item: JobFitInsight) -> "JobFitInsightResponse":
        return cls(text=item.text, citation_ids=list(item.citation_ids))


class JobFitAnalysisResponse(BaseModel):
    id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    version: int
    prompt_version: str
    provider: str
    model: str
    generator_version: str
    generation_identity: str
    overall_fit: JobFitLevel
    overall_fit_reason: JobFitInsightResponse
    strong_matches: list[JobFitInsightResponse]
    transferable_evidence: list[JobFitInsightResponse]
    critical_gaps: list[JobFitInsightResponse]
    non_blocking_gaps: list[JobFitInsightResponse]
    resume_actions: list[JobFitInsightResponse]
    project_deep_dive_risks: list[JobFitInsightResponse]
    interview_focus: list[JobFitInsightResponse]
    unknowns: list[JobFitInsightResponse]
    citations: list[JobFitCitationResponse]
    generated_at: datetime

    @classmethod
    def from_domain(cls, analysis: JobFitAnalysis) -> "JobFitAnalysisResponse":
        def insights(items: tuple[JobFitInsight, ...]) -> list[JobFitInsightResponse]:
            return [JobFitInsightResponse.from_domain(item) for item in items]

        return cls(
            id=analysis.id,
            report_id=analysis.report_id,
            report_version=analysis.report_version,
            decision_case_id=analysis.decision_case_id,
            version=analysis.version,
            prompt_version=analysis.prompt_version,
            provider=analysis.provider,
            model=analysis.model,
            generator_version=analysis.generator_version,
            generation_identity=analysis.generation_identity,
            overall_fit=analysis.overall_fit,
            overall_fit_reason=JobFitInsightResponse.from_domain(analysis.overall_fit_reason),
            strong_matches=insights(analysis.strong_matches),
            transferable_evidence=insights(analysis.transferable_evidence),
            critical_gaps=insights(analysis.critical_gaps),
            non_blocking_gaps=insights(analysis.non_blocking_gaps),
            resume_actions=insights(analysis.resume_actions),
            project_deep_dive_risks=insights(analysis.project_deep_dive_risks),
            interview_focus=insights(analysis.interview_focus),
            unknowns=insights(analysis.unknowns),
            citations=[JobFitCitationResponse.from_domain(item) for item in analysis.citations],
            generated_at=analysis.generated_at,
        )


class CreateApplicationDecisionRequest(BaseModel):
    status: ApplicationDecisionStatus
    reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_skip_reason(self) -> "CreateApplicationDecisionRequest":
        if self.status is ApplicationDecisionStatus.SKIP and not (self.reason or "").strip():
            raise ValueError("reason is required when status is skip")
        return self


class ApplicationDecisionResponse(BaseModel):
    id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    resume_version_id: UUID
    resume_version: int
    status: ApplicationDecisionStatus
    reason: str | None
    actor_id: UUID
    decided_at: datetime

    @classmethod
    def from_domain(cls, decision: ApplicationDecision) -> "ApplicationDecisionResponse":
        return cls.model_validate(decision, from_attributes=True)


@decision_router.post("", response_model=DecisionCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_decision_case(
    payload: CreateDecisionCaseRequest,
    response: Response,
    user: User = Depends(get_current_user),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    posting_repository: JobPostingRepository = Depends(get_job_posting_repository),
    requirement_repository: JobRequirementSnapshotRepository = Depends(
        get_job_requirement_snapshot_repository
    ),
    profile_repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
    resume_repository: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> DecisionCaseResponse:
    result = await CreateDecisionCaseUseCase(
        case_repository,
        posting_repository,
        requirement_repository,
        profile_repository,
        resume_repository,
    ).execute(
        CreateDecisionCaseCommand(
            owner_id=user.id,
            rule_set_version=RULE_SET_VERSION,
            **payload.model_dump(),
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return DecisionCaseResponse.from_domain(result.decision_case)


@decision_router.get("/{case_id}", response_model=DecisionAnalysisResponse)
async def analyze_decision_case(
    case_id: UUID,
    user: User = Depends(get_current_user),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    requirement_repository: JobRequirementSnapshotRepository = Depends(
        get_job_requirement_snapshot_repository
    ),
    profile_repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
) -> DecisionAnalysisResponse:
    result = await AnalyzeDecisionCaseUseCase(
        case_repository,
        requirement_repository,
        profile_repository,
    ).execute(AnalyzeDecisionCaseQuery(owner_id=user.id, case_id=case_id))
    return DecisionAnalysisResponse(
        decision=DecisionCaseResponse.from_domain(result.decision_case),
        rule_set_version=result.evaluation.rule_set_version,
        rule_results=[RuleResultResponse.from_domain(item) for item in result.evaluation.results],
    )


@decision_router.post("/{case_id}/reports", response_model=DecisionReportResponse)
async def generate_decision_report(
    case_id: UUID,
    user: User = Depends(get_current_user),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
    requirement_repository: JobRequirementSnapshotRepository = Depends(
        get_job_requirement_snapshot_repository
    ),
    profile_repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    source_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> DecisionReportResponse:
    result = await GenerateStoredDecisionReportUseCase(
        case_repository,
        report_repository,
        requirement_repository,
        profile_repository,
    ).execute(
        GenerateStoredDecisionReportCommand(
            owner_id=user.id,
            case_id=case_id,
            generator_version=REPORT_GENERATOR_VERSION,
        )
    )
    attachment = await _company_assessment_use_cases(
        assessment_repository,
        report_repository,
        case_repository,
        snapshot_repository,
        source_repository,
        artifact_repository,
    ).get(user.id, result.report.id)
    return DecisionReportResponse.from_domain(
        result.report,
        None if attachment is None else _company_assessment_response(attachment),
    )


@report_router.get("", response_model=DecisionReportListResponse)
async def list_decision_reports(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    source_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> DecisionReportListResponse:
    result = await ListDecisionReportsUseCase(repository).execute(
        ListDecisionReportsQuery(owner_id=user.id, page=page, page_size=page_size)
    )
    attachments = {
        item.id: await _company_assessment_use_cases(
            assessment_repository,
            repository,
            case_repository,
            snapshot_repository,
            source_repository,
            artifact_repository,
        ).get(user.id, item.id)
        for item in result.items
    }
    return DecisionReportListResponse(
        items=[
            DecisionReportResponse.from_domain(
                item,
                (
                    None
                    if attachments[item.id] is None
                    else _company_assessment_response(attachments[item.id])
                ),
            )
            for item in result.items
        ],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@report_router.get("/{report_id}", response_model=DecisionReportResponse)
async def get_decision_report(
    report_id: UUID,
    user: User = Depends(get_current_user),
    repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    source_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> DecisionReportResponse:
    report = await GetDecisionReportUseCase(repository).execute(
        GetDecisionReportQuery(owner_id=user.id, report_id=report_id)
    )
    attachment = await _company_assessment_use_cases(
        assessment_repository,
        repository,
        case_repository,
        snapshot_repository,
        source_repository,
        artifact_repository,
    ).get(user.id, report.id)
    return DecisionReportResponse.from_domain(
        report,
        None if attachment is None else _company_assessment_response(attachment),
    )


@report_router.post(
    "/{report_id}/job-fit-analysis",
    response_model=JobFitAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_job_fit_analysis(
    report_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    analysis_repository: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    model: ModelPort = Depends(get_model_port),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    profile_repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
    resume_repository: ResumeVersionRepository = Depends(get_resume_version_repository),
    posting_repository: JobPostingRepository = Depends(get_job_posting_repository),
    requirement_repository: JobRequirementSnapshotRepository = Depends(
        get_job_requirement_snapshot_repository
    ),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
) -> JobFitAnalysisResponse:
    report = await report_repository.get_by_id(report_id)
    if report is None:
        raise ApplicationError("Decision report not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
    decision_case = await case_repository.get_by_id(report.decision_case_id)
    if decision_case is None:
        raise ApplicationError(
            "Fixed job-fit inputs are unavailable",
            error_code=ErrorCode.DECISION_INPUT_UNAVAILABLE,
        )
    profile = await profile_repository.get_version(decision_case.candidate_profile_version)
    resume = await resume_repository.get_by_identity(
        decision_case.resume_version_id, decision_case.resume_version
    )
    posting = await posting_repository.get_by_id(decision_case.job_posting_id)
    requirements = await requirement_repository.get_by_identity(
        decision_case.job_requirement_snapshot_id,
        decision_case.job_requirement_snapshot_version,
    )
    if profile is None or resume is None or posting is None or requirements is None:
        raise ApplicationError(
            "Fixed job-fit inputs are unavailable",
            error_code=ErrorCode.DECISION_INPUT_UNAVAILABLE,
        )
    company_snapshot = None
    company_assessment = await assessment_repository.get_for_report(report.id)
    if company_assessment is not None:
        company_snapshot = await snapshot_repository.get_by_identity(
            company_assessment.company_snapshot_id,
            company_assessment.company_snapshot_version,
        )
        if company_snapshot is None:
            raise ApplicationError(
                "Fixed company input is unavailable",
                error_code=ErrorCode.COMPANY_ASSESSMENT_UNAVAILABLE,
            )
    result = await GenerateJobFitAnalysisUseCase(analysis_repository, model).execute(
        GenerateJobFitAnalysisCommand(owner_id=user.id),
        decision_case=decision_case,
        report=report,
        profile=profile,
        resume=resume,
        posting=posting,
        requirements=requirements,
        company_snapshot=company_snapshot,
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return JobFitAnalysisResponse.from_domain(result.analysis)


@report_router.get(
    "/{report_id}/job-fit-analysis",
    response_model=JobFitAnalysisResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "No AI job-fit analysis"}},
)
async def get_job_fit_analysis(
    report_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    analysis_repository: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
) -> JobFitAnalysisResponse | Response:
    report = await report_repository.get_by_id(report_id)
    if report is None or report.owner_id != user.id:
        raise ApplicationError("Decision report not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
    analysis = await analysis_repository.get_for_report(report.id)
    if analysis is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return JobFitAnalysisResponse.from_domain(analysis)


@report_router.post(
    "/{report_id}/company-assessment",
    response_model=CompanyAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_assessment(
    report_id: UUID,
    payload: CreateCompanyAssessmentRequest,
    response: Response,
    user: User = Depends(get_current_user),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    source_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanyAssessmentResponse:
    result, replayed = await _company_assessment_use_cases(
        assessment_repository,
        report_repository,
        case_repository,
        snapshot_repository,
        source_repository,
        artifact_repository,
    ).create(
        CreateCompanyAssessmentCommand(
            owner_id=user.id,
            report_id=report_id,
            company_snapshot_id=payload.company_snapshot_id,
            company_snapshot_version=payload.company_snapshot_version,
            generator_version="m4-company-assessment-v1",
        )
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
    return _company_assessment_response(result)


@report_router.get(
    "/{report_id}/company-assessment",
    response_model=CompanyAssessmentResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "No company assessment attached"}},
)
async def get_company_assessment(
    report_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    assessment_repository: CompanyAssessmentRepository = Depends(get_company_assessment_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    snapshot_repository: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    source_repository: SourceDocumentRepository = Depends(get_source_document_repository),
    artifact_repository: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanyAssessmentResponse | Response:
    result = await _company_assessment_use_cases(
        assessment_repository,
        report_repository,
        case_repository,
        snapshot_repository,
        source_repository,
        artifact_repository,
    ).get(user.id, report_id)
    if result is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return _company_assessment_response(result)


@report_router.get(
    "/{report_id}/decision",
    response_model=ApplicationDecisionResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "No decision recorded"}},
)
async def get_application_decision(
    report_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    repository: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
) -> ApplicationDecisionResponse | Response:
    decision = await GetApplicationDecisionUseCase(repository, report_repository).execute(
        GetApplicationDecisionQuery(owner_id=user.id, report_id=report_id)
    )
    if decision is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return ApplicationDecisionResponse.from_domain(decision)


@report_router.post(
    "/{report_id}/decision",
    response_model=ApplicationDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_decision(
    report_id: UUID,
    payload: CreateApplicationDecisionRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    repository: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    report_repository: DecisionReportRepository = Depends(get_decision_report_repository),
    case_repository: DecisionCaseRepository = Depends(get_decision_case_repository),
    audit_repository: AuditEventRepository = Depends(get_audit_event_repository),
    transaction: Transaction = Depends(get_transaction),
) -> ApplicationDecisionResponse:
    result = await CreateApplicationDecisionUseCase(
        repository,
        report_repository,
        case_repository,
        audit_repository,
        transaction,
    ).execute(
        CreateApplicationDecisionCommand(
            owner_id=user.id,
            actor_id=user.id,
            report_id=report_id,
            status=payload.status,
            reason=payload.reason,
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ApplicationDecisionResponse.from_domain(result.decision)
