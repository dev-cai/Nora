from unittest.mock import AsyncMock

import pytest
from app.apps.api.dependencies.common import get_session
from app.apps.api.dependencies.followup import get_application_decision_repository
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.opportunity import get_job_posting_repository
from app.apps.api.dependencies.transaction import get_transaction
from app.domain.base.exceptions import InfrastructureError
from app.domain.identity import User
from app.infrastructure.database import (
    SqlAlchemyApplicationDecisionRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyTransaction,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
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


def test_request_dependencies_share_and_close_one_session() -> None:
    app = FastAPI()
    session = AsyncMock(spec=AsyncSession)
    context_calls = 0
    exited = False

    class SessionContext:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *_args: object) -> None:
            nonlocal exited
            exited = True

    def session_factory() -> SessionContext:
        nonlocal context_calls
        context_calls += 1
        return SessionContext()

    app.state.session_factory = session_factory

    @app.get("/session-identity")
    async def session_identity(
        first: AsyncSession = Depends(get_session),
        second: AsyncSession = Depends(get_session),
    ) -> dict[str, bool]:
        return {"shared": first is second}

    with TestClient(app) as client:
        response = client.get("/session-identity")

    assert response.json() == {"shared": True}
    assert context_calls == 1
    assert exited
