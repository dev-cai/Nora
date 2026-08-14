"""Career API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session
from app.domain.identity import User
from app.infrastructure.database import (
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyResumeVersionRepository,
)
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository


def get_candidate_profile_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CandidateProfileRepository:
    return SqlAlchemyCandidateProfileRepository(session, user.id)


def get_resume_version_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumeVersionRepository:
    return SqlAlchemyResumeVersionRepository(session, user.id)
