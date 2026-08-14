"""Create and read fixed CompanyAssessment report attachments."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.decision import CompanyAssessment, CompanyAssessmentStatus
from app.domain.knowledge import ArtifactStatus
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceTier,
    Freshness,
)
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
)
from app.ports.knowledge import ArtifactRepository, SourceDocumentRepository
from app.ports.opportunity import CompanySnapshotRepository


@dataclass(frozen=True, slots=True)
class CreateCompanyAssessmentCommand:
    owner_id: UUID
    report_id: UUID
    company_snapshot_id: UUID
    company_snapshot_version: int
    generator_version: str


@dataclass(frozen=True, slots=True)
class ReportCompanyAssessment:
    assessment: CompanyAssessment
    snapshot: CompanySnapshot


class CompanyAssessmentUseCases:
    def __init__(
        self,
        assessments: CompanyAssessmentRepository,
        reports: DecisionReportRepository,
        cases: DecisionCaseRepository,
        snapshots: CompanySnapshotRepository,
        sources: SourceDocumentRepository,
        artifacts: ArtifactRepository,
    ) -> None:
        self.assessments = assessments
        self.reports = reports
        self.cases = cases
        self.snapshots = snapshots
        self.sources = sources
        self.artifacts = artifacts

    async def create(
        self, command: CreateCompanyAssessmentCommand
    ) -> tuple[ReportCompanyAssessment, bool]:
        report = await self.reports.get_by_id(command.report_id)
        if report is None or report.owner_id != command.owner_id:
            raise ApplicationError(
                "Decision report not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        decision_case = await self.cases.get_by_id(report.decision_case_id)
        snapshot = await self.snapshots.get_by_identity(
            command.company_snapshot_id, command.company_snapshot_version
        )
        if (
            decision_case is None
            or decision_case.owner_id != command.owner_id
            or snapshot is None
            or snapshot.owner_id != command.owner_id
        ):
            raise ApplicationError(
                "Company assessment input not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        assessment_status, status_reason = await self._status(command.owner_id, snapshot)
        candidate = CompanyAssessment.create(
            owner_id=command.owner_id,
            report_id=report.id,
            report_version=report.version,
            decision_case_id=decision_case.id,
            company_snapshot_id=snapshot.id,
            company_snapshot_version=snapshot.version,
            status=assessment_status,
            status_reason=status_reason,
            generator_version=command.generator_version,
        )
        existing = await self.assessments.get_for_report(report.id)
        if existing is not None:
            if existing.generation_identity != candidate.generation_identity:
                raise ApplicationError(
                    "Report already has a different company assessment",
                    error_code=ErrorCode.COMPANY_ASSESSMENT_CONFLICT,
                )
            return ReportCompanyAssessment(existing, snapshot), True
        try:
            stored = await self.assessments.add(candidate)
            await self.assessments.commit()
        except InfrastructureError as exc:
            if exc.error_code is not ErrorCode.COMPANY_ASSESSMENT_CONFLICT:
                raise
            replay = await self.assessments.get_by_generation(candidate.generation_identity)
            if replay is None:
                raise
            return ReportCompanyAssessment(replay, snapshot), True
        return ReportCompanyAssessment(stored, snapshot), False

    async def get(self, owner_id: UUID, report_id: UUID) -> ReportCompanyAssessment | None:
        report = await self.reports.get_by_id(report_id)
        if report is None or report.owner_id != owner_id:
            raise ApplicationError(
                "Decision report not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        assessment = await self.assessments.get_for_report(report_id)
        if assessment is None:
            return None
        snapshot = await self.snapshots.get_by_identity(
            assessment.company_snapshot_id, assessment.company_snapshot_version
        )
        if snapshot is None:
            raise InfrastructureError(
                "Fixed company snapshot is unavailable",
                error_code=ErrorCode.COMPANY_ASSESSMENT_UNAVAILABLE,
            )
        return ReportCompanyAssessment(assessment, snapshot)

    async def _status(
        self, owner_id: UUID, snapshot: CompanySnapshot
    ) -> tuple[CompanyAssessmentStatus, str]:
        source = await self.sources.get_by_id(snapshot.source.source_id)
        artifact = None if source is None else await self.artifacts.get_by_id(source.artifact_id)
        if (
            source is None
            or source.owner_id != owner_id
            or source.version != snapshot.source.source_version
            or artifact is None
            or artifact.owner_id != owner_id
            or artifact.version != source.artifact_version
            or artifact.status is not ArtifactStatus.AVAILABLE
        ):
            return CompanyAssessmentStatus.UNKNOWN, "source_unavailable"
        statuses = (snapshot.size_status, snapshot.industry_status, snapshot.review_status)
        if CompanyFieldStatus.CONFLICTED in statuses:
            return CompanyAssessmentStatus.CONFLICTED, "conflicted_fields"
        if snapshot.freshness is Freshness.STALE:
            return CompanyAssessmentStatus.STALE, "source_stale"
        if snapshot.freshness is Freshness.UNKNOWN:
            return CompanyAssessmentStatus.UNKNOWN, "source_freshness_unknown"
        if snapshot.source.source_tier is CompanySourceTier.ANONYMOUS_PLATFORM:
            return CompanyAssessmentStatus.UNKNOWN, "anonymous_source"
        if CompanyFieldStatus.SUPERSEDED in statuses:
            return CompanyAssessmentStatus.UNKNOWN, "superseded_fields"
        if CompanyFieldStatus.UNKNOWN in statuses:
            return CompanyAssessmentStatus.UNKNOWN, "incomplete_fields"
        return CompanyAssessmentStatus.AVAILABLE, "fixed_snapshot"
