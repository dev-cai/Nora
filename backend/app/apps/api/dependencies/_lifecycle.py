"""Internal request lifecycle providers used by API composition."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base.exceptions import ErrorCode, NoraError
from app.infrastructure.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise NoraError("Database is not configured", error_code=ErrorCode.DATABASE_UNAVAILABLE)
    async with session_factory() as session:
        yield session
