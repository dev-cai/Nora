"""SQLAlchemy implementation of the Application transaction port."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base.exceptions import ErrorCode, InfrastructureError


class SqlAlchemyTransaction:
    """Complete transaction segments on one request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise InfrastructureError(
                "Database is unavailable",
                error_code=ErrorCode.DATABASE_UNAVAILABLE,
            ) from exc

    async def rollback(self) -> None:
        try:
            await self.session.rollback()
        except SQLAlchemyError as exc:
            raise InfrastructureError(
                "Database is unavailable",
                error_code=ErrorCode.DATABASE_UNAVAILABLE,
            ) from exc
