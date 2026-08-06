"""API 依赖：数据库会话和认证上下文。"""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.identity import IdentityService
from app.domain.base.exceptions import NoraError
from app.domain.identity import User
from app.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer
from app.infrastructure.database import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
    SqlAlchemyResumeVersionRepository,
    SqlAlchemyUserRepository,
)
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository
from app.ports.governance import AuditEventRepository
from app.ports.opportunity import JobPostingRepository, JobRequirementSnapshotRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """从应用生命周期创建的会话工厂提供会话。"""

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise NoraError("Database is not configured", error_code="database_unavailable")
    async with session_factory() as session:
        yield session


def get_identity_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IdentityService:
    """组装 Identity 用例及其基础设施端口。"""

    settings = request.app.state.settings
    return IdentityService(
        SqlAlchemyUserRepository(session),
        Argon2PasswordHasher(),
        JwtTokenIssuer(settings.auth_secret_key, settings.auth_access_token_minutes),
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: IdentityService = Depends(get_identity_service),
) -> User:
    """校验 Bearer Token 并返回当前用户。"""

    if credentials is None:
        raise NoraError("Authentication required", error_code="authentication_failed")
    user = await service.current_user(credentials.credentials)
    request.state.current_user = user
    return user


def get_job_posting_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobPostingRepository:
    """组装当前认证用户范围内的岗位快照 Repository。"""

    return SqlAlchemyJobPostingRepository(session, user.id)


def get_candidate_profile_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CandidateProfileRepository:
    """组装当前认证用户范围内的 CandidateProfile Repository。"""

    return SqlAlchemyCandidateProfileRepository(session, user.id)


def get_resume_version_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumeVersionRepository:
    """组装当前认证用户范围内的 ResumeVersion Repository。"""

    return SqlAlchemyResumeVersionRepository(session, user.id)


def get_job_requirement_snapshot_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobRequirementSnapshotRepository:
    """组装当前认证用户范围内的岗位要求快照 Repository。"""

    return SqlAlchemyJobRequirementSnapshotRepository(session, user.id)


def get_audit_event_repository(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> AuditEventRepository:
    """组装与业务写入共享事务的只追加审计 Repository。"""

    return SqlAlchemyAuditEventRepository(session)
