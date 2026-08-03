"""用户范围内岗位快照创建与读取 API。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app.application.opportunity import (
    CreateJobPostingCommand,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
    ListJobPostingsQuery,
    ListJobPostingsUseCase,
)
from app.apps.api.dependencies import (
    get_audit_event_repository,
    get_current_user,
    get_job_posting_repository,
)
from app.domain.identity import User
from app.domain.opportunity import (
    UNKNOWN_COMPANY_NAME,
    UNKNOWN_JOB_TITLE,
    UNKNOWN_LOCATION,
    JobPosting,
    JobPostingStatus,
    JobSourceType,
)
from app.ports.governance import AuditEventRepository
from app.ports.opportunity import JobPostingRepository

router = APIRouter(prefix="/job-postings", tags=["job-postings"])
MetadataField = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
JdTextField = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100_000)
]


class CreateJobPostingRequest(BaseModel):
    """手工或 URL 来源的岗位正文快照输入。"""

    jd_text: JdTextField
    job_title: MetadataField = UNKNOWN_JOB_TITLE
    company_name: MetadataField = UNKNOWN_COMPANY_NAME
    location: MetadataField = UNKNOWN_LOCATION
    source_url: str | None = Field(default=None, max_length=2_048)
    source_type: JobSourceType = JobSourceType.MANUAL


class JobPostingResponse(BaseModel):
    """岗位快照的稳定公开字段。"""

    id: UUID
    jd_text: str
    job_title: str
    company_name: str
    location: str
    summary: str
    source_type: JobSourceType
    source_url: str | None
    status: JobPostingStatus
    version: int
    created_at: datetime

    @classmethod
    def from_job_posting(cls, posting: JobPosting) -> "JobPostingResponse":
        return cls(
            id=posting.id,
            jd_text=posting.jd_text,
            job_title=posting.job_title,
            company_name=posting.company_name,
            location=posting.location,
            summary=posting.text_summary,
            source_type=posting.source_type,
            source_url=posting.source_url,
            status=posting.status,
            version=posting.version,
            created_at=posting.created_at,
        )


class JobPostingListResponse(BaseModel):
    """用户范围岗位快照的稳定分页响应。"""

    items: list[JobPostingResponse]
    page: int
    page_size: int
    total: int


@router.post("", response_model=JobPostingResponse, status_code=status.HTTP_201_CREATED)
async def create_job_posting(
    payload: CreateJobPostingRequest,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
    user: User = Depends(get_current_user),
    repository: JobPostingRepository = Depends(get_job_posting_repository),
    audit_repository: AuditEventRepository = Depends(get_audit_event_repository),
) -> JobPostingResponse:
    result = await CreateJobPostingUseCase(repository, audit_repository).execute(
        CreateJobPostingCommand(
            owner_id=user.id,
            idempotency_key=idempotency_key,
            jd_text=payload.jd_text,
            job_title=payload.job_title,
            company_name=payload.company_name,
            location=payload.location,
            source_type=payload.source_type,
            source_url=payload.source_url,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return JobPostingResponse.from_job_posting(result.job_posting)


@router.get("", response_model=JobPostingListResponse)
async def list_job_postings(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    repository: JobPostingRepository = Depends(get_job_posting_repository),
) -> JobPostingListResponse:
    result = await ListJobPostingsUseCase(repository).execute(
        ListJobPostingsQuery(owner_id=user.id, page=page, page_size=page_size)
    )
    return JobPostingListResponse(
        items=[JobPostingResponse.from_job_posting(posting) for posting in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{job_posting_id}", response_model=JobPostingResponse)
async def get_job_posting(
    job_posting_id: UUID,
    user: User = Depends(get_current_user),
    repository: JobPostingRepository = Depends(get_job_posting_repository),
) -> JobPostingResponse:
    posting = await GetJobPostingUseCase(repository).execute(
        GetJobPostingQuery(owner_id=user.id, job_posting_id=job_posting_id)
    )
    return JobPostingResponse.from_job_posting(posting)
