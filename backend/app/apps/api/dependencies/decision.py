"""Decision API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session
from app.domain.identity import User
from app.infrastructure.database import (
    SqlAlchemyCompanyAssessmentRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
)
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
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
