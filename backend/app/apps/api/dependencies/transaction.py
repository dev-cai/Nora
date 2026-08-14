"""Existing request-scoped Transaction composition dependency."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.api.dependencies.common import get_session
from app.infrastructure.database import SqlAlchemyTransaction
from app.ports.transaction import Transaction


def get_transaction(session: AsyncSession = Depends(get_session)) -> Transaction:
    return SqlAlchemyTransaction(session)
