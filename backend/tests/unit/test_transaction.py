from unittest.mock import AsyncMock

import pytest
from app.apps.api.dependencies import (
    get_application_decision_repository,
    get_audit_event_repository,
    get_job_posting_repository,
    get_transaction,
)
from app.domain.base.exceptions import InfrastructureError
from app.domain.identity import User
from app.infrastructure.database import (
    SqlAlchemyApplicationDecisionRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyTransaction,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_sqlalchemy_transaction_delegates_to_session() -> None:
    session = AsyncMock(spec=AsyncSession)
    transaction = SqlAlchemyTransaction(session)

    await transaction.commit()
    await transaction.rollback()

    session.commit.assert_awaited_once_with()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["commit", "rollback"])
async def test_sqlalchemy_transaction_maps_database_failures(operation: str) -> None:
    session = AsyncMock(spec=AsyncSession)
    getattr(session, operation).side_effect = SQLAlchemyError("database failed")
    transaction = SqlAlchemyTransaction(session)

    with pytest.raises(InfrastructureError) as error:
        await getattr(transaction, operation)()

    assert error.value.error_code == "database_unavailable"
    assert str(error.value) == "Database is unavailable"


def test_composition_reuses_one_session_for_transaction_and_repositories() -> None:
    session = AsyncMock(spec=AsyncSession)
    user = User.create("transaction-owner", "transaction-owner@example.com")

    transaction = get_transaction(session)
    job_postings = get_job_posting_repository(session, user)
    decisions = get_application_decision_repository(session, user)
    audits = get_audit_event_repository(session, user)

    assert isinstance(transaction, SqlAlchemyTransaction)
    assert isinstance(job_postings, SqlAlchemyJobPostingRepository)
    assert isinstance(decisions, SqlAlchemyApplicationDecisionRepository)
    assert isinstance(audits, SqlAlchemyAuditEventRepository)
    assert transaction.session is session
    assert job_postings.session is session
    assert decisions.session is session
    assert audits.session is session
