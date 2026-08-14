"""Versioned deterministic DecisionReport generation use cases."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.career import CandidateProfile
from app.domain.decision import DecisionCase, DecisionReport, evaluate_decision_rules
from app.domain.opportunity import JobRequirementSnapshot
from app.ports.decision import DecisionReportRepository


@dataclass(frozen=True, slots=True)
class GenerateDecisionReportCommand:
    owner_id: UUID
    generator_version: str


@dataclass(frozen=True, slots=True)
class GenerateDecisionReportResult:
    report: DecisionReport
    replayed: bool


class GenerateDecisionReportUseCase:
    """Generate and idempotently publish a deterministic report."""

    def __init__(self, repository: DecisionReportRepository) -> None:
        self.repository = repository

    async def execute(
        self,
        command: GenerateDecisionReportCommand,
        *,
        decision_case: DecisionCase,
        candidate_profile: CandidateProfile,
        requirements: JobRequirementSnapshot,
    ) -> GenerateDecisionReportResult:
        if decision_case.owner_id != command.owner_id:
            raise ApplicationError("Decision case not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        generator_version = DecisionReport.normalize_generator_version(command.generator_version)
        existing = await self.repository.get_by_generation(
            decision_case.id,
            decision_case.rule_set_version,
            generator_version,
        )
        if existing is not None:
            return GenerateDecisionReportResult(report=existing, replayed=True)

        evaluation = evaluate_decision_rules(decision_case, candidate_profile, requirements)
        version = await self.repository.next_version(decision_case.id)
        report = DecisionReport.generate(
            decision_case=decision_case,
            evaluation=evaluation,
            version=version,
            generator_version=generator_version,
        )
        try:
            stored = await self.repository.add(report)
            await self.repository.commit()
        except InfrastructureError as exc:
            if exc.error_code not in {
                "decision_report_generation_conflict",
                "decision_report_version_conflict",
            }:
                raise
            replay = await self.repository.get_by_generation(
                decision_case.id,
                decision_case.rule_set_version,
                report.generator_version,
            )
            if replay is None:
                raise
            return GenerateDecisionReportResult(report=replay, replayed=True)
        return GenerateDecisionReportResult(report=stored, replayed=False)
