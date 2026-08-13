"""Authenticated immutable CompanySnapshot API."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field

from app.application.opportunity import (
    AppendCompanySnapshotCommand,
    CompanySnapshotUseCases,
    CreateCompanySnapshotCommand,
    GetCompanySnapshotQuery,
)
from app.apps.api.dependencies import (
    get_artifact_repository,
    get_company_snapshot_repository,
    get_current_user,
    get_source_document_repository,
)
from app.domain.identity import User
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceTier,
    Freshness,
)
from app.ports.knowledge import ArtifactRepository, SourceDocumentRepository
from app.ports.opportunity import CompanySnapshotRepository

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanySnapshotValuesRequest(BaseModel):
    size: str | None = Field(default=None, max_length=200)
    size_status: CompanyFieldStatus
    industry: str | None = Field(default=None, max_length=200)
    industry_status: CompanyFieldStatus
    review_summary: str | None = Field(default=None, max_length=2_000)
    review_status: CompanyFieldStatus
    source_id: UUID
    source_version: int = Field(ge=1)
    source_tier: CompanySourceTier


class CreateCompanySnapshotRequest(CompanySnapshotValuesRequest):
    company_name: str = Field(min_length=1, max_length=200)


class AppendCompanySnapshotRequest(CompanySnapshotValuesRequest):
    expected_version: int = Field(ge=1)


class CompanySourceReferenceResponse(BaseModel):
    id: UUID
    version: int
    tier: CompanySourceTier
    kind: str
    acquisition_method: str
    license_note: str
    acquired_at: datetime
    published_at: datetime | None
    content_sha256: str


class CompanySnapshotResponse(BaseModel):
    id: UUID
    version: int
    company_name: str
    size: str | None
    size_status: CompanyFieldStatus
    industry: str | None
    industry_status: CompanyFieldStatus
    review_summary: str | None
    review_status: CompanyFieldStatus
    source: CompanySourceReferenceResponse
    freshness: Freshness
    content_sha256: str
    created_at: datetime

    @classmethod
    def from_domain(cls, snapshot: CompanySnapshot) -> "CompanySnapshotResponse":
        source = snapshot.source
        return cls(
            id=snapshot.id,
            version=snapshot.version,
            company_name=snapshot.company_name,
            size=snapshot.size,
            size_status=snapshot.size_status,
            industry=snapshot.industry,
            industry_status=snapshot.industry_status,
            review_summary=snapshot.review_summary,
            review_status=snapshot.review_status,
            source=CompanySourceReferenceResponse(
                id=source.source_id,
                version=source.source_version,
                tier=source.source_tier,
                kind=source.source_kind,
                acquisition_method=source.acquisition_method,
                license_note=source.license_note,
                acquired_at=source.acquired_at,
                published_at=source.published_at,
                content_sha256=source.content_sha256,
            ),
            freshness=snapshot.freshness,
            content_sha256=snapshot.content_sha256,
            created_at=snapshot.created_at,
        )


def _use_cases(
    snapshots: CompanySnapshotRepository,
    sources: SourceDocumentRepository,
    artifacts: ArtifactRepository,
) -> CompanySnapshotUseCases:
    return CompanySnapshotUseCases(snapshots, sources, artifacts)


@router.post("", response_model=CompanySnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_company_snapshot(
    payload: CreateCompanySnapshotRequest,
    user: User = Depends(get_current_user),
    snapshots: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanySnapshotResponse:
    snapshot = await _use_cases(snapshots, sources, artifacts).create(
        CreateCompanySnapshotCommand(owner_id=user.id, **payload.model_dump())
    )
    return CompanySnapshotResponse.from_domain(snapshot)


@router.post(
    "/{snapshot_id}/versions",
    response_model=CompanySnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def append_company_snapshot(
    snapshot_id: UUID,
    payload: AppendCompanySnapshotRequest,
    user: User = Depends(get_current_user),
    snapshots: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanySnapshotResponse:
    snapshot = await _use_cases(snapshots, sources, artifacts).append(
        AppendCompanySnapshotCommand(
            owner_id=user.id, snapshot_id=snapshot_id, **payload.model_dump()
        )
    )
    return CompanySnapshotResponse.from_domain(snapshot)


@router.get("/{snapshot_id}", response_model=CompanySnapshotResponse)
async def get_latest_company_snapshot(
    snapshot_id: UUID,
    user: User = Depends(get_current_user),
    snapshots: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanySnapshotResponse:
    snapshot = await _use_cases(snapshots, sources, artifacts).get(
        GetCompanySnapshotQuery(owner_id=user.id, snapshot_id=snapshot_id)
    )
    return CompanySnapshotResponse.from_domain(snapshot)


@router.get("/{snapshot_id}/versions", response_model=list[CompanySnapshotResponse])
async def list_company_snapshot_versions(
    snapshot_id: UUID,
    user: User = Depends(get_current_user),
    snapshots: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
) -> list[CompanySnapshotResponse]:
    values = await _use_cases(snapshots, sources, artifacts).list_versions(
        GetCompanySnapshotQuery(owner_id=user.id, snapshot_id=snapshot_id)
    )
    return [CompanySnapshotResponse.from_domain(value) for value in values]


@router.get("/{snapshot_id}/versions/{version}", response_model=CompanySnapshotResponse)
async def get_company_snapshot_version(
    snapshot_id: UUID,
    version: int = Path(ge=1),
    user: User = Depends(get_current_user),
    snapshots: CompanySnapshotRepository = Depends(get_company_snapshot_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
) -> CompanySnapshotResponse:
    snapshot = await _use_cases(snapshots, sources, artifacts).get(
        GetCompanySnapshotQuery(owner_id=user.id, snapshot_id=snapshot_id, version=version)
    )
    return CompanySnapshotResponse.from_domain(snapshot)
