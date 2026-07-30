"""用户范围内岗位快照创建与读取 API。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, Field

from nora.application.opportunity import (
    CreateJobPostingCommand,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
)
from nora.apps.api.dependencies import get_current_user, get_job_posting_repository
from nora.domain.identity import User
from nora.domain.opportunity import JobPosting, JobSourceType
from nora.ports.opportunity import JobPostingRepository

router = APIRouter(prefix="/job-postings", tags=["job-postings"])


class CreateJobPostingRequest(BaseModel):
    """手工或 URL 来源的岗位正文快照输入。"""

    jd_text: str = Field(min_length=1, max_length=100_000)
    source_url: str | None = Field(default=None, max_length=2_048)
    source_type: JobSourceType = JobSourceType.MANUAL


class JobPostingResponse(BaseModel):
    """岗位快照的稳定公开字段。"""

    id: UUID
    summary: str
    created_at: datetime

    @classmethod
    def from_job_posting(cls, posting: JobPosting) -> "JobPostingResponse":
        return cls(
            id=posting.id,
            summary=posting.text_summary,
            created_at=posting.created_at,
        )


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
) -> JobPostingResponse:
    result = await CreateJobPostingUseCase(repository).execute(
        CreateJobPostingCommand(
            owner_id=user.id,
            idempotency_key=idempotency_key,
            jd_text=payload.jd_text,
            source_type=payload.source_type,
            source_url=payload.source_url,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return JobPostingResponse.from_job_posting(result.job_posting)


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
