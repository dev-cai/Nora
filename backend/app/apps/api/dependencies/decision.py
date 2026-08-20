"""Decision API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyCompanyAssessmentRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
    SqlAlchemyJobFitAnalysisRepository,
)
from app.infrastructure.model import create_model_adapter
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.model import ModelPort


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
