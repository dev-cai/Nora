"""Follow-up API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session
from app.domain.identity import User
from app.infrastructure.database import (
    SqlAlchemyApplicationDecisionRepository,
    SqlAlchemyApplicationRecordRepository,
    SqlAlchemyApplicationRecordTransitionRepository,
    SqlAlchemyInterviewCaseRepository,
    SqlAlchemyInterviewPreparationRepository,
    SqlAlchemyInterviewReviewRepository,
    SqlAlchemyMemoryCandidateRepository,
    SqlAlchemyMessageDraftRepository,
    SqlAlchemyResumePdfRepository,
    SqlAlchemyResumeVariantRepository,
    SqlAlchemyTemplateDefinitionRepository,
)
from app.infrastructure.pdf_renderer import WeasyPrintResumePdfRenderer
from app.ports.followup import (
    ApplicationDecisionRepository,
    ApplicationRecordRepository,
    ApplicationRecordTransitionRepository,
    InterviewCaseRepository,
    InterviewPreparationRepository,
    InterviewReviewRepository,
    MemoryCandidateRepository,
    MessageDraftRepository,
    ResumePdfRenderer,
    ResumePdfRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)


def get_application_decision_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApplicationDecisionRepository:
    return SqlAlchemyApplicationDecisionRepository(session, user.id)


def get_application_record_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApplicationRecordRepository:
    return SqlAlchemyApplicationRecordRepository(session, user.id)


def get_application_record_transition_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApplicationRecordTransitionRepository:
    return SqlAlchemyApplicationRecordTransitionRepository(session, user.id)


def get_interview_case_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> InterviewCaseRepository:
    return SqlAlchemyInterviewCaseRepository(session, user.id)


def get_interview_preparation_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> InterviewPreparationRepository:
    return SqlAlchemyInterviewPreparationRepository(session, user.id)


def get_interview_review_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> InterviewReviewRepository:
    return SqlAlchemyInterviewReviewRepository(session, user.id)


def get_memory_candidate_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MemoryCandidateRepository:
    return SqlAlchemyMemoryCandidateRepository(session, user.id)


def get_resume_variant_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumeVariantRepository:
    return SqlAlchemyResumeVariantRepository(session, user.id)


def get_message_draft_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageDraftRepository:
    return SqlAlchemyMessageDraftRepository(session, user.id)


def get_resume_pdf_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumePdfRepository:
    return SqlAlchemyResumePdfRepository(session, user.id)


def get_resume_pdf_renderer() -> ResumePdfRenderer:
    return WeasyPrintResumePdfRenderer()


def get_template_definition_repository(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> TemplateDefinitionRepository:
    return SqlAlchemyTemplateDefinitionRepository(session)
