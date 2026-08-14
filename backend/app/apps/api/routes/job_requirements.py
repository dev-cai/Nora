"""用户范围内岗位要求快照的保存与读取 API。"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status
from pydantic import BaseModel, Field

from app.application.opportunity import (
    GetJobRequirementSnapshotQuery,
    GetJobRequirementSnapshotUseCase,
    ListJobRequirementSnapshotsQuery,
    ListJobRequirementSnapshotsResult,
    ListJobRequirementSnapshotsUseCase,
    SaveJobRequirementSnapshotCommand,
    SaveJobRequirementSnapshotUseCase,
)
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.opportunity import (
    get_job_posting_repository,
    get_job_requirement_snapshot_repository,
)
from app.domain.identity import User
from app.domain.opportunity import (
    JobRequirementSnapshot,
    RequirementConfirmationStatus,
    RequirementSourceType,
)
from app.ports.opportunity import (
    JobPostingRepository,
    JobRequirementSnapshotRepository,
)

router = APIRouter(prefix="/job-postings/{job_posting_id}/requirements", tags=["job-requirements"])


class RequirementFactModel(BaseModel):
    """单个岗位要求字段的事实结构。"""

    value: int | str | list[str] | None = None
    confirmation_status: RequirementConfirmationStatus
    source_type: RequirementSourceType
    source_range: str | None = Field(default=None, max_length=64)


class SaveJobRequirementSnapshotRequest(BaseModel):
    """创建或追加版本的结构化岗位要求输入。"""

    content: dict[str, RequirementFactModel]
    job_posting_version: int = Field(default=1, ge=1)


class JobRequirementSnapshotResponse(BaseModel):
    """岗位要求快照版本的稳定公开字段。"""

    id: UUID
    job_posting_id: UUID
    job_posting_version: int
    version: int
    content: dict[str, RequirementFactModel]
    content_hash: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: JobRequirementSnapshot) -> "JobRequirementSnapshotResponse":
        return cls(
            id=snapshot.id,
            job_posting_id=snapshot.job_posting_id,
            job_posting_version=snapshot.job_posting_version,
            version=snapshot.version,
            content=snapshot.content,
            content_hash=snapshot.content_hash,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )


class JobRequirementSnapshotListResponse(BaseModel):
    """岗位要求快照版本的稳定分页响应。"""

    items: list[JobRequirementSnapshotResponse]
    page: int
    page_size: int
    total: int


@router.post("", response_model=JobRequirementSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def save_job_requirement_snapshot(
    job_posting_id: UUID,
    payload: SaveJobRequirementSnapshotRequest,
    response: Response,
    user: User = Depends(get_current_user),
    repository: JobRequirementSnapshotRepository = Depends(get_job_requirement_snapshot_repository),
    posting_repository: JobPostingRepository = Depends(get_job_posting_repository),
) -> JobRequirementSnapshotResponse:
    result = await SaveJobRequirementSnapshotUseCase(repository, posting_repository).execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=user.id,
            job_posting_id=job_posting_id,
            job_posting_version=payload.job_posting_version,
            content=_facts_to_content(payload.content),
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return JobRequirementSnapshotResponse.from_snapshot(result.snapshot)


@router.get("/latest", response_model=JobRequirementSnapshotResponse)
async def get_latest_job_requirement_snapshot(
    job_posting_id: UUID,
    user: User = Depends(get_current_user),
    repository: JobRequirementSnapshotRepository = Depends(get_job_requirement_snapshot_repository),
) -> JobRequirementSnapshotResponse:
    snapshot = await GetJobRequirementSnapshotUseCase(repository).execute(
        GetJobRequirementSnapshotQuery(owner_id=user.id, job_posting_id=job_posting_id)
    )
    return JobRequirementSnapshotResponse.from_snapshot(snapshot)


@router.get("", response_model=JobRequirementSnapshotListResponse)
async def list_job_requirement_snapshots(
    job_posting_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    repository: JobRequirementSnapshotRepository = Depends(get_job_requirement_snapshot_repository),
) -> JobRequirementSnapshotListResponse:
    result = await ListJobRequirementSnapshotsUseCase(repository).execute(
        ListJobRequirementSnapshotsQuery(
            owner_id=user.id, job_posting_id=job_posting_id, page=page, page_size=page_size
        )
    )
    return _list_response(result)


@router.get("/{version}", response_model=JobRequirementSnapshotResponse)
async def get_job_requirement_snapshot_version(
    job_posting_id: UUID,
    version: Annotated[int, Path(ge=1)],
    user: User = Depends(get_current_user),
    repository: JobRequirementSnapshotRepository = Depends(get_job_requirement_snapshot_repository),
) -> JobRequirementSnapshotResponse:
    snapshot = await GetJobRequirementSnapshotUseCase(repository).execute(
        GetJobRequirementSnapshotQuery(
            owner_id=user.id, job_posting_id=job_posting_id, version=version
        )
    )
    return JobRequirementSnapshotResponse.from_snapshot(snapshot)


def _facts_to_content(content: dict[str, RequirementFactModel]) -> dict[str, Any]:
    return {
        field: {
            "value": fact.value,
            "confirmation_status": fact.confirmation_status.value,
            "source_type": fact.source_type.value,
            "source_range": fact.source_range,
        }
        for field, fact in content.items()
    }


def _list_response(
    result: ListJobRequirementSnapshotsResult,
) -> JobRequirementSnapshotListResponse:
    return JobRequirementSnapshotListResponse(
        items=[JobRequirementSnapshotResponse.from_snapshot(snapshot) for snapshot in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )
