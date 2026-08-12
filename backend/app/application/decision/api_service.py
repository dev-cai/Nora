"""Application orchestration for the public decision and report API."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.decision import (
    DecisionCase,
    DecisionReport,
    RuleSetEvaluation,
    evaluate_decision_rules,
)
from app.ports.career import CandidateProfileRepository
from app.ports.decision import DecisionCaseRepository, DecisionReportRepository
from app.ports.opportunity import JobRequirementSnapshotRepository

from .report_service import (
    GenerateDecisionReportCommand,
    GenerateDecisionReportResult,
    GenerateDecisionReportUseCase,
)


@dataclass(frozen=True, slots=True)
class AnalyzeDecisionCaseQuery:
    owner_id: UUID
    case_id: UUID


@dataclass(frozen=True, slots=True)
class DecisionCaseAnalysis:
    decision_case: DecisionCase
    evaluation: RuleSetEvaluation


@dataclass(frozen=True, slots=True)
class GenerateStoredDecisionReportCommand:
    owner_id: UUID
    case_id: UUID
    generator_version: str


@dataclass(frozen=True, slots=True)
class GetDecisionReportQuery:
    owner_id: UUID
    report_id: UUID


@dataclass(frozen=True, slots=True)
class ListDecisionReportsQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListDecisionReportsResult:
    items: tuple[DecisionReport, ...]
    page: int
    page_size: int
    total: int


class AnalyzeDecisionCaseUseCase:
    """Load a fixed case input set and synchronously evaluate its rules."""

    def __init__(
        self,
        case_repository: DecisionCaseRepository,
        requirement_repository: JobRequirementSnapshotRepository,
        profile_repository: CandidateProfileRepository,
    ) -> None:
        self.case_repository = case_repository
        self.requirement_repository = requirement_repository
        self.profile_repository = profile_repository

    async def execute(self, query: AnalyzeDecisionCaseQuery) -> DecisionCaseAnalysis:
        decision_case = await self.case_repository.get_by_id(query.case_id)
        if decision_case is None or decision_case.owner_id != query.owner_id:
            raise ApplicationError("Decision case not found", error_code="entity_not_found")
        requirements = await self.requirement_repository.get_by_identity(
            decision_case.job_requirement_snapshot_id,
            decision_case.job_requirement_snapshot_version,
        )
        profile = await self.profile_repository.get_version(decision_case.candidate_profile_version)
        if requirements is None or profile is None:
            raise InfrastructureError(
                "Decision case inputs are unavailable",
                error_code="decision_input_unavailable",
            )
        return DecisionCaseAnalysis(
            decision_case=decision_case,
            evaluation=evaluate_decision_rules(decision_case, profile, requirements),
        )


class GenerateStoredDecisionReportUseCase:
    """Resolve one case's fixed inputs and idempotently publish its report."""

    def __init__(
        self,
        case_repository: DecisionCaseRepository,
        report_repository: DecisionReportRepository,
        requirement_repository: JobRequirementSnapshotRepository,
        profile_repository: CandidateProfileRepository,
    ) -> None:
        self.case_repository = case_repository
        self.report_repository = report_repository
        self.requirement_repository = requirement_repository
        self.profile_repository = profile_repository

    async def execute(
        self, command: GenerateStoredDecisionReportCommand
    ) -> GenerateDecisionReportResult:
        decision_case = await self.case_repository.get_by_id(command.case_id)
        if decision_case is None or decision_case.owner_id != command.owner_id:
            raise ApplicationError("Decision case not found", error_code="entity_not_found")
        requirements = await self.requirement_repository.get_by_identity(
            decision_case.job_requirement_snapshot_id,
            decision_case.job_requirement_snapshot_version,
        )
        profile = await self.profile_repository.get_version(decision_case.candidate_profile_version)
        if requirements is None or profile is None:
            raise InfrastructureError(
                "Decision case inputs are unavailable",
                error_code="decision_input_unavailable",
            )
        return await GenerateDecisionReportUseCase(self.report_repository).execute(
            GenerateDecisionReportCommand(
                owner_id=command.owner_id,
                generator_version=command.generator_version,
            ),
            decision_case=decision_case,
            candidate_profile=profile,
            requirements=requirements,
        )


class GetDecisionReportUseCase:
    def __init__(self, repository: DecisionReportRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetDecisionReportQuery) -> DecisionReport:
        report = await self.repository.get_by_id(query.report_id)
        if report is None or report.owner_id != query.owner_id:
            raise ApplicationError("Decision report not found", error_code="entity_not_found")
        return report


class ListDecisionReportsUseCase:
    """List current-user reports newest first with stable page pagination."""

    def __init__(self, repository: DecisionReportRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListDecisionReportsQuery) -> ListDecisionReportsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError(
                "Page must be at least 1 and page_size must be between 1 and 100",
                error_code="invalid_pagination",
            )
        items = await self.repository.list(
            offset=(query.page - 1) * query.page_size,
            limit=query.page_size,
        )
        return ListDecisionReportsResult(
            items=tuple(items),
            page=query.page,
            page_size=query.page_size,
            total=await self.repository.count(),
        )
