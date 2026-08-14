"""Create and read immutable apply/skip decisions."""

import json
from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.followup import ApplicationDecision, ApplicationDecisionStatus
from app.domain.governance import AuditAction, AuditEvent
from app.ports.decision import DecisionCaseRepository, DecisionReportRepository
from app.ports.followup import ApplicationDecisionRepository
from app.ports.governance import AuditEventRepository
from app.ports.transaction import Transaction


@dataclass(frozen=True, slots=True)
class CreateApplicationDecisionCommand:
    owner_id: UUID
    actor_id: UUID
    report_id: UUID
    status: ApplicationDecisionStatus
    reason: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CreateApplicationDecisionResult:
    decision: ApplicationDecision
    replayed: bool


@dataclass(frozen=True, slots=True)
class GetApplicationDecisionQuery:
    owner_id: UUID
    report_id: UUID


class CreateApplicationDecisionUseCase:
    def __init__(
        self,
        repository: ApplicationDecisionRepository,
        report_repository: DecisionReportRepository,
        case_repository: DecisionCaseRepository,
        audit_repository: AuditEventRepository,
        transaction: Transaction,
    ) -> None:
        self.repository = repository
        self.report_repository = report_repository
        self.case_repository = case_repository
        self.audit_repository = audit_repository
        self.transaction = transaction

    async def execute(
        self, command: CreateApplicationDecisionCommand
    ) -> CreateApplicationDecisionResult:
        report = await self.report_repository.get_by_id(command.report_id)
        if report is None or report.owner_id != command.owner_id:
            raise ApplicationError("Decision report not found", error_code="entity_not_found")
        decision_case = await self.case_repository.get_by_id(report.decision_case_id)
        if decision_case is None or decision_case.owner_id != command.owner_id:
            raise ApplicationError("Decision case not found", error_code="entity_not_found")

        candidate = ApplicationDecision.create(
            owner_id=command.owner_id,
            actor_id=command.actor_id,
            report_id=report.id,
            report_version=report.version,
            decision_case_id=decision_case.id,
            resume_version_id=decision_case.resume_version_id,
            resume_version=decision_case.resume_version,
            status=command.status,
            reason=command.reason,
            idempotency_key=command.idempotency_key,
        )
        existing_by_key = await self.repository.get_by_idempotency_key(candidate.idempotency_key)
        if existing_by_key is not None:
            return _resolve_replay(existing_by_key, candidate)
        existing_for_report = await self.repository.get_by_report_id(report.id)
        if existing_for_report is not None:
            return _resolve_report_decision(existing_for_report, candidate)

        try:
            stored = await self.repository.add(candidate)
            await self.audit_repository.add(
                AuditEvent.create(
                    actor_id=command.actor_id,
                    action=AuditAction.CREATE,
                    target_type="application_decision",
                    target_id=stored.id,
                    target_version=1,
                    after_summary=_audit_summary(stored),
                    idempotency_key=stored.idempotency_key,
                )
            )
            await self.transaction.commit()
        except InfrastructureError as exc:
            await self.transaction.rollback()
            if exc.error_code not in {
                "application_decision_key_taken",
                "application_decision_conflict",
            }:
                raise
            existing_by_key = await self.repository.get_by_idempotency_key(
                candidate.idempotency_key
            )
            if existing_by_key is not None:
                return _resolve_replay(existing_by_key, candidate)
            existing_for_report = await self.repository.get_by_report_id(report.id)
            if existing_for_report is not None:
                return _resolve_report_decision(existing_for_report, candidate)
            raise InfrastructureError(
                "Could not recover application decision",
                error_code="application_decision_persistence_failed",
            ) from exc
        except Exception:
            await self.transaction.rollback()
            raise
        return CreateApplicationDecisionResult(decision=stored, replayed=False)


class GetApplicationDecisionUseCase:
    def __init__(
        self,
        repository: ApplicationDecisionRepository,
        report_repository: DecisionReportRepository,
    ) -> None:
        self.repository = repository
        self.report_repository = report_repository

    async def execute(self, query: GetApplicationDecisionQuery) -> ApplicationDecision | None:
        report = await self.report_repository.get_by_id(query.report_id)
        if report is None or report.owner_id != query.owner_id:
            raise ApplicationError("Decision report not found", error_code="entity_not_found")
        return await self.repository.get_by_report_id(query.report_id)


def _resolve_replay(
    existing: ApplicationDecision, candidate: ApplicationDecision
) -> CreateApplicationDecisionResult:
    if not existing.has_same_request(candidate):
        raise ApplicationError(
            "Idempotency key was already used with different content",
            error_code="idempotency_conflict",
        )
    return CreateApplicationDecisionResult(decision=existing, replayed=True)


def _resolve_report_decision(
    existing: ApplicationDecision, candidate: ApplicationDecision
) -> CreateApplicationDecisionResult:
    if existing.has_same_request(candidate):
        return CreateApplicationDecisionResult(decision=existing, replayed=True)
    raise ApplicationError(
        "The report already has a different decision",
        error_code="application_decision_conflict",
    )


def _audit_summary(decision: ApplicationDecision) -> str:
    return json.dumps(
        {
            "report_id": str(decision.report_id),
            "report_version": decision.report_version,
            "status": decision.status.value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
