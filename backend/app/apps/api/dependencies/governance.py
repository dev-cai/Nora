"""Governance API composition dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_current_user, get_session
from app.domain.identity import User
from app.infrastructure.database import SqlAlchemyAuditEventRepository
from app.ports.governance import AuditEventRepository


def get_audit_event_repository(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> AuditEventRepository:
    return SqlAlchemyAuditEventRepository(session)
