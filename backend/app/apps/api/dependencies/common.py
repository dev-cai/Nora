"""Shared request-scoped API dependencies."""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.identity import IdentityService
from app.apps.api.dependencies._lifecycle import get_session, get_settings
from app.apps.api.dependencies.identity import get_identity_service
from app.domain.base.exceptions import NoraError
from app.domain.identity import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: IdentityService = Depends(get_identity_service),
) -> User:
    if credentials is None:
        raise NoraError("Authentication required", error_code="authentication_failed")
    user = await service.current_user(credentials.credentials)
    request.state.current_user = user
    return user


__all__ = ("get_current_user", "get_session", "get_settings")
