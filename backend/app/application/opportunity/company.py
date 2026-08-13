"""CompanySnapshot creation, version append, and exact-version reads."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.knowledge import ArtifactStatus
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceReference,
    CompanySourceTier,
)
from app.ports.knowledge import ArtifactRepository, SourceDocumentRepository
from app.ports.opportunity import CompanySnapshotRepository


@dataclass(frozen=True, slots=True)
class CompanySnapshotValues:
    size: str | None
    size_status: CompanyFieldStatus
    industry: str | None
    industry_status: CompanyFieldStatus
    review_summary: str | None
    review_status: CompanyFieldStatus
    source_id: UUID
    source_version: int
    source_tier: CompanySourceTier


@dataclass(frozen=True, slots=True)
class CreateCompanySnapshotCommand(CompanySnapshotValues):
    owner_id: UUID
    company_name: str


@dataclass(frozen=True, slots=True)
class AppendCompanySnapshotCommand(CompanySnapshotValues):
    owner_id: UUID
    snapshot_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class GetCompanySnapshotQuery:
    owner_id: UUID
    snapshot_id: UUID
    version: int | None = None


class CompanySnapshotUseCases:
    def __init__(
        self,
        snapshots: CompanySnapshotRepository,
        sources: SourceDocumentRepository,
        artifacts: ArtifactRepository,
    ) -> None:
        self.snapshots = snapshots
        self.sources = sources
        self.artifacts = artifacts

    async def create(self, command: CreateCompanySnapshotCommand) -> CompanySnapshot:
        source = await self._fixed_source(command.owner_id, command)
        snapshot = CompanySnapshot.create(
            owner_id=command.owner_id,
            company_name=command.company_name,
            size=command.size,
            size_status=command.size_status,
            industry=command.industry,
            industry_status=command.industry_status,
            review_summary=command.review_summary,
            review_status=command.review_status,
            source=source,
        )
        return await self._store(snapshot)

    async def append(self, command: AppendCompanySnapshotCommand) -> CompanySnapshot:
        latest = await self.snapshots.get_latest(command.snapshot_id)
        if latest is None or latest.owner_id != command.owner_id:
            raise ApplicationError("Company snapshot not found", error_code="entity_not_found")
        if latest.version != command.expected_version:
            raise ApplicationError(
                "Company snapshot version conflict",
                error_code="company_snapshot_version_conflict",
            )
        source = await self._fixed_source(command.owner_id, command)
        return await self._store(
            latest.append_version(
                size=command.size,
                size_status=command.size_status,
                industry=command.industry,
                industry_status=command.industry_status,
                review_summary=command.review_summary,
                review_status=command.review_status,
                source=source,
            )
        )

    async def get(self, query: GetCompanySnapshotQuery) -> CompanySnapshot:
        snapshot = (
            await self.snapshots.get_latest(query.snapshot_id)
            if query.version is None
            else await self.snapshots.get_by_identity(query.snapshot_id, query.version)
        )
        if snapshot is None or snapshot.owner_id != query.owner_id:
            raise ApplicationError("Company snapshot not found", error_code="entity_not_found")
        return snapshot

    async def list_versions(self, query: GetCompanySnapshotQuery) -> tuple[CompanySnapshot, ...]:
        if await self.snapshots.get_latest(query.snapshot_id) is None:
            raise ApplicationError("Company snapshot not found", error_code="entity_not_found")
        return tuple(await self.snapshots.list_versions(query.snapshot_id))

    async def _fixed_source(
        self, owner_id: UUID, values: CompanySnapshotValues
    ) -> CompanySourceReference:
        source = await self.sources.get_by_id(values.source_id)
        if source is None or source.owner_id != owner_id or source.version != values.source_version:
            raise ApplicationError("Source not found", error_code="entity_not_found")
        artifact = await self.artifacts.get_by_id(source.artifact_id)
        if (
            artifact is None
            or artifact.owner_id != owner_id
            or artifact.version != source.artifact_version
            or artifact.status is not ArtifactStatus.AVAILABLE
        ):
            raise ApplicationError("Source not found", error_code="entity_not_found")
        return CompanySourceReference.create(
            source_id=source.id,
            source_version=source.version,
            source_tier=values.source_tier,
            source_kind=source.source_kind.value,
            acquisition_method=source.acquisition_method,
            license_note=source.license_note,
            acquired_at=source.acquired_at,
            published_at=source.published_at,
            content_sha256=source.content_sha256,
        )

    async def _store(self, snapshot: CompanySnapshot) -> CompanySnapshot:
        try:
            stored = await self.snapshots.add(snapshot)
            await self.snapshots.commit()
            return stored
        except InfrastructureError as exc:
            if exc.error_code == "company_snapshot_version_conflict":
                raise ApplicationError(
                    "Company snapshot version conflict",
                    error_code="company_snapshot_version_conflict",
                ) from exc
            raise
