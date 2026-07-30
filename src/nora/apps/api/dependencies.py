"""API 依赖：数据库会话和认证上下文。"""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from nora.application.identity import IdentityService
from nora.domain.base.exceptions import NoraError
from nora.domain.identity import User
from nora.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer
from nora.infrastructure.database import SqlAlchemyJobPostingRepository, SqlAlchemyUserRepository
from nora.ports.opportunity import JobPostingRepository

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
