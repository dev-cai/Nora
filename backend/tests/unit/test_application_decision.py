from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.followup import (
    CreateApplicationDecisionCommand,
    CreateApplicationDecisionUseCase,
    GetApplicationDecisionQuery,
    GetApplicationDecisionUseCase,
)
from app.domain.base.exceptions import (
    ApplicationError,
    DomainError,
    ErrorCode,
    InfrastructureError,
)
from app.domain.decision import DecisionCase, DecisionReport
from app.domain.followup import ApplicationDecision, ApplicationDecisionStatus
from app.domain.governance import AuditEvent


def test_application_decision_requires_skip_reason_and_normalizes_content() -> None:
    with pytest.raises(DomainError) as error:
        _decision(status=ApplicationDecisionStatus.SKIP, reason="   ")
    assert error.value.error_code == "skip_reason_required"

    decision = _decision(status=ApplicationDecisionStatus.SKIP, reason="  地点 不合适  ")

    assert decision.reason == "地点 不合适"
    assert decision.report_version == 2
    assert decision.resume_version == 3
    assert decision.decided_at == datetime(2026, 8, 12, tzinfo=timezone.utc)


def test_application_decision_restore_rejects_changed_fingerprint() -> None:
    decision = _decision(status=ApplicationDecisionStatus.APPLY, reason=None)

    with pytest.raises(DomainError) as error:
        ApplicationDecision.restore(
            decision_id=decision.id,
            owner_id=decision.owner_id,
            actor_id=decision.actor_id,
            report_id=decision.report_id,
            report_version=decision.report_version,
            decision_case_id=decision.decision_case_id,
            resume_version_id=decision.resume_version_id,
            resume_version=decision.resume_version,
            status=decision.status,
            reason=decision.reason,
            idempotency_key=decision.idempotency_key,
            request_fingerprint="0" * 64,
            decided_at=decision.decided_at,
        )
    assert error.value.error_code == "invalid_application_decision_fingerprint"


@pytest.mark.asyncio
async def test_create_application_decision_is_idempotent_and_audited() -> None:
    owner_id = uuid4()
    report = _report(owner_id=owner_id)
    case = _case(owner_id=owner_id, case_id=report.decision_case_id)
    repository = FakeApplicationDecisionRepository()
    audit_repository = FakeAuditRepository()
    transaction = FakeTransaction()
    use_case = CreateApplicationDecisionUseCase(
        repository,
        FakeReportRepository(report),
        FakeCaseRepository(case),
        audit_repository,
        transaction,
    )
    command = CreateApplicationDecisionCommand(
        owner_id=owner_id,
        actor_id=owner_id,
        report_id=report.id,
        status=ApplicationDecisionStatus.SKIP,
        reason="岗位地点不合适",
        idempotency_key="decision-1",
    )

    first = await use_case.execute(command)
    replay = await use_case.execute(command)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.decision.id == first.decision.id
    assert first.decision.report_version == report.version
    assert first.decision.resume_version_id == case.resume_version_id
    assert len(audit_repository.events) == 1
    assert audit_repository.events[0].idempotency_key == "decision-1"
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_create_application_decision_rejects_conflicting_status_and_key_reuse() -> None:
    owner_id = uuid4()
    report = _report(owner_id=owner_id)
    case = _case(owner_id=owner_id, case_id=report.decision_case_id)
    repository = FakeApplicationDecisionRepository()
    transaction = FakeTransaction()
    use_case = CreateApplicationDecisionUseCase(
        repository,
        FakeReportRepository(report),
        FakeCaseRepository(case),
        FakeAuditRepository(),
        transaction,
    )
    await use_case.execute(
        CreateApplicationDecisionCommand(
            owner_id=owner_id,
            actor_id=owner_id,
            report_id=report.id,
            status=ApplicationDecisionStatus.SKIP,
            reason="地点不合适",
            idempotency_key="decision-1",
        )
    )

    with pytest.raises(ApplicationError) as report_conflict:
        await use_case.execute(
            CreateApplicationDecisionCommand(
                owner_id=owner_id,
                actor_id=owner_id,
                report_id=report.id,
                status=ApplicationDecisionStatus.APPLY,
                reason=None,
                idempotency_key="decision-2",
            )
        )
    assert report_conflict.value.error_code == "application_decision_conflict"

    second_report = _report(owner_id=owner_id)
    use_case = CreateApplicationDecisionUseCase(
        repository,
        FakeReportRepository(second_report),
        FakeCaseRepository(_case(owner_id=owner_id, case_id=second_report.decision_case_id)),
        FakeAuditRepository(),
        transaction,
    )
    with pytest.raises(ApplicationError) as key_conflict:
        await use_case.execute(
            CreateApplicationDecisionCommand(
                owner_id=owner_id,
                actor_id=owner_id,
                report_id=second_report.id,
                status=ApplicationDecisionStatus.APPLY,
                reason=None,
                idempotency_key="decision-1",
            )
        )
    assert key_conflict.value.error_code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_create_application_decision_rolls_back_before_concurrent_recovery() -> None:
    owner_id = uuid4()
    report = _report(owner_id=owner_id)
    transaction = FakeTransaction()
    repository = RacingApplicationDecisionRepository(transaction)

    result = await CreateApplicationDecisionUseCase(
        repository,
        FakeReportRepository(report),
        FakeCaseRepository(_case(owner_id=owner_id, case_id=report.decision_case_id)),
        FakeAuditRepository(),
        transaction,
    ).execute(
        CreateApplicationDecisionCommand(
            owner_id=owner_id,
            actor_id=owner_id,
            report_id=report.id,
            status=ApplicationDecisionStatus.APPLY,
            reason=None,
            idempotency_key="decision-race",
        )
    )

    assert result.replayed is True
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_create_application_decision_rolls_back_when_audit_write_fails() -> None:
    owner_id = uuid4()
    report = _report(owner_id=owner_id)
    transaction = FakeTransaction()

    with pytest.raises(RuntimeError, match="audit failed"):
        await CreateApplicationDecisionUseCase(
            FakeApplicationDecisionRepository(),
            FakeReportRepository(report),
            FakeCaseRepository(_case(owner_id=owner_id, case_id=report.decision_case_id)),
            FailingAuditRepository(),
            transaction,
        ).execute(
            CreateApplicationDecisionCommand(
                owner_id=owner_id,
                actor_id=owner_id,
                report_id=report.id,
                status=ApplicationDecisionStatus.APPLY,
                reason=None,
                idempotency_key="decision-audit-failure",
            )
        )

    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_get_application_decision_hides_foreign_report() -> None:
    owner_id = uuid4()
    report = _report(owner_id=owner_id)
    use_case = GetApplicationDecisionUseCase(
        FakeApplicationDecisionRepository(), FakeReportRepository(report)
    )

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(GetApplicationDecisionQuery(owner_id=uuid4(), report_id=report.id))
    assert error.value.error_code == "entity_not_found"


class FakeApplicationDecisionRepository:
    def __init__(self) -> None:
        self.decisions: list[ApplicationDecision] = []

    async def add(self, decision: ApplicationDecision) -> ApplicationDecision:
        self.decisions.append(decision)
        return decision

    async def get_by_report_id(self, report_id: UUID) -> ApplicationDecision | None:
        return next((item for item in self.decisions if item.report_id == report_id), None)

    async def get_by_idempotency_key(self, key: str) -> ApplicationDecision | None:
        return next((item for item in self.decisions if item.idempotency_key == key), None)


class FakeReportRepository:
    def __init__(self, report: DecisionReport) -> None:
        self.report = report

    async def get_by_id(self, report_id: UUID) -> DecisionReport | None:
        return self.report if self.report.id == report_id else None


class FakeCaseRepository:
    def __init__(self, decision_case: DecisionCase) -> None:
        self.decision_case = decision_case

    async def get_by_id(self, case_id: UUID) -> DecisionCase | None:
        return self.decision_case if self.decision_case.id == case_id else None


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def add(self, event: object) -> object:
        self.events.append(event)
        return event


class FailingAuditRepository:
    async def add(self, event: AuditEvent) -> AuditEvent:
        raise RuntimeError("audit failed")


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RacingApplicationDecisionRepository(FakeApplicationDecisionRepository):
    def __init__(self, transaction: FakeTransaction) -> None:
        super().__init__()
        self.transaction = transaction
        self.claimed = False

    async def add(self, decision: ApplicationDecision) -> ApplicationDecision:
        await super().add(decision)
        self.claimed = True
        raise InfrastructureError(
            "Concurrent request won",
            error_code=ErrorCode.APPLICATION_DECISION_KEY_TAKEN,
        )

    async def get_by_idempotency_key(self, key: str) -> ApplicationDecision | None:
        if self.claimed and self.transaction.rollbacks == 0:
            raise AssertionError("recovery query ran before rollback")
        return await super().get_by_idempotency_key(key)


def _decision(*, status: ApplicationDecisionStatus, reason: str | None) -> ApplicationDecision:
    return ApplicationDecision.create(
        owner_id=uuid4(),
        actor_id=uuid4(),
        report_id=uuid4(),
        report_version=2,
        decision_case_id=uuid4(),
        resume_version_id=uuid4(),
        resume_version=3,
        status=status,
        reason=reason,
        idempotency_key="decision-key",
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def _case(*, owner_id: UUID, case_id: UUID) -> DecisionCase:
    created = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=uuid4(),
        job_posting_version=1,
        job_requirement_snapshot_id=uuid4(),
        job_requirement_snapshot_version=1,
        candidate_profile_id=uuid4(),
        candidate_profile_version=1,
        resume_version_id=uuid4(),
        resume_version=3,
        rule_set_version="m3-rules-v1",
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    return DecisionCase.restore(
        case_id=case_id,
        owner_id=created.owner_id,
        job_posting_id=created.job_posting_id,
        job_posting_version=created.job_posting_version,
        job_requirement_snapshot_id=created.job_requirement_snapshot_id,
        job_requirement_snapshot_version=created.job_requirement_snapshot_version,
        candidate_profile_id=created.candidate_profile_id,
        candidate_profile_version=created.candidate_profile_version,
        resume_version_id=created.resume_version_id,
        resume_version=created.resume_version,
        rule_set_version=created.rule_set_version,
        input_fingerprint=created.input_fingerprint,
        status=created.status,
        created_at=created.created_at,
        completed_at=created.completed_at,
        failure_code=created.failure_code,
        failure_message=created.failure_message,
    )


def _report(*, owner_id: UUID) -> DecisionReport:
    return DecisionReport.restore(
        report_id=uuid4(),
        owner_id=owner_id,
        decision_case_id=uuid4(),
        version=2,
        rule_set_version="m3-rules-v1",
        generator_version="m3-report-v1",
        content={
            "summary": {"match": 0, "partial": 0, "mismatch": 0, "unknown": 0},
            "fact": [],
            "rule_result": [
                {
                    "rule_id": "skills.coverage",
                    "rule_version": "1",
                    "status": "unknown",
                    "reason": "输入不足",
                    "citation_ids": [],
                }
            ],
            "unknown": [],
            "recommendation": [],
            "citation": [],
            "satisfied_conditions": [],
            "gaps": [],
            "risks": [],
            "next_steps": [],
        },
        generated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
