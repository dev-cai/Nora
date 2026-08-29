"""Decision API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime import JdImportAgent
from app.application.decision import (
    GenerateJobFitAnalysisUseCase,
    GenerateStoredJobFitAnalysisUseCase,
)
from app.apps.api.dependencies.career import (
    get_candidate_profile_repository,
    get_resume_version_repository,
)
from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.apps.api.dependencies.opportunity import (
    get_company_snapshot_repository,
    get_job_posting_repository,
    get_job_requirement_snapshot_repository,
)
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyCompanyAssessmentRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
    SqlAlchemyJobFitAnalysisRepository,
)
from app.infrastructure.model import create_model_adapter
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.model import ModelPort
from app.ports.opportunity import (
    CompanySnapshotRepository,
    JobPostingRepository,
    JobRequirementSnapshotRepository,
)


def get_decision_case_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DecisionCaseRepository:
    return SqlAlchemyDecisionCaseRepository(session, user.id)


def get_decision_report_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DecisionReportRepository:
    return SqlAlchemyDecisionReportRepository(session, user.id)


def get_company_assessment_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompanyAssessmentRepository:
    return SqlAlchemyCompanyAssessmentRepository(session, user.id)


def get_job_fit_analysis_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobFitAnalysisRepository:
    return SqlAlchemyJobFitAnalysisRepository(session, user.id)


def get_model_port(settings: Settings = Depends(get_settings)) -> ModelPort:
    return create_model_adapter(settings)


def get_generate_stored_job_fit_analysis_use_case(
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
) -> GenerateStoredJobFitAnalysisUseCase:
    return GenerateStoredJobFitAnalysisUseCase(
        reports=report_repository,
        cases=case_repository,
        profiles=profile_repository,
        resumes=resume_repository,
        postings=posting_repository,
        requirements=requirement_repository,
        assessments=assessment_repository,
        snapshots=snapshot_repository,
        generator=GenerateJobFitAnalysisUseCase(analysis_repository, model),
    )


def get_jd_import_agent(model: ModelPort = Depends(get_model_port)) -> JdImportAgent:
    return JdImportAgent(model)
