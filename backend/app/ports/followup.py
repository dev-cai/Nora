"""Application & Follow-up repository contracts."""

from typing import Protocol
from uuid import UUID

from app.domain.followup import ApplicationDecision


class ApplicationDecisionRepository(Protocol):
    async def add(self, decision: ApplicationDecision) -> ApplicationDecision: ...

    async def get_by_report_id(self, report_id: UUID) -> ApplicationDecision | None: ...

    async def get_by_idempotency_key(self, key: str) -> ApplicationDecision | None: ...

    async def commit(self) -> None: ...
