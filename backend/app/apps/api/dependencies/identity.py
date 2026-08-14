"""Identity API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.identity import IdentityService
from app.apps.api.dependencies._lifecycle import get_session, get_settings
from app.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer
from app.infrastructure.config import Settings
from app.infrastructure.database import SqlAlchemyUserRepository


def get_identity_service(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> IdentityService:
    return IdentityService(
        SqlAlchemyUserRepository(session),
        Argon2PasswordHasher(),
        JwtTokenIssuer(settings.auth_secret_key, settings.auth_access_token_minutes),
    )
