"""用户确认主档的不可变 ResumeVersion 发布与读取 API。"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, StringConstraints

from app.application.career import (
    GetResumeVersionQuery,
    GetResumeVersionUseCase,
    ListResumeVersionsQuery,
    ListResumeVersionsUseCase,
    PublishResumeVersionCommand,
    PublishResumeVersionUseCase,
)
from app.apps.api.dependencies import (
    get_candidate_profile_repository,
    get_current_user,
    get_resume_version_repository,
)
from app.domain.career import ResumeVersion
from app.domain.identity import User
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository

router = APIRouter(prefix="/resumes", tags=["resumes"])
ResumeTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PublishResumeVersionRequest(BaseModel):
    """从指定主档版本发布简历的请求。"""

    title: ResumeTitle
    profile_version: int = Field(ge=1)


class ResumeVersionResponse(BaseModel):
    """ResumeVersion 的稳定公开响应。"""

    id: UUID
    owner_id: UUID
    version: int
    candidate_profile_id: UUID
    profile_version: int
    title: str
    content: dict[str, Any]
    published_at: datetime

    @classmethod
    def from_domain(cls, resume: ResumeVersion) -> "ResumeVersionResponse":
        return cls(
            id=resume.id,
            owner_id=resume.owner_id,
            version=resume.version,
            candidate_profile_id=resume.candidate_profile_id,
            profile_version=resume.profile_version,
            title=resume.title,
            content=resume.content,
            published_at=resume.published_at,
        )


class ResumeVersionListResponse(BaseModel):
    """ResumeVersion 用户范围分页响应。"""

    items: list[ResumeVersionResponse]
    page: int
    page_size: int
    total: int


@router.post("", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
async def publish_resume_version(
    payload: PublishResumeVersionRequest,
    user: User = Depends(get_current_user),
    profile_repository: CandidateProfileRepository = Depends(get_candidate_profile_repository),
    resume_repository: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVersionResponse:
    resume = await PublishResumeVersionUseCase(profile_repository, resume_repository).execute(
        PublishResumeVersionCommand(
            owner_id=user.id,
            profile_version=payload.profile_version,
            title=payload.title,
        )
    )
    return ResumeVersionResponse.from_domain(resume)


@router.get("", response_model=ResumeVersionListResponse)
async def list_resume_versions(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    repository: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVersionListResponse:
    result = await ListResumeVersionsUseCase(repository).execute(
        ListResumeVersionsQuery(owner_id=user.id, page=page, page_size=page_size)
    )
    return ResumeVersionListResponse(
        items=[ResumeVersionResponse.from_domain(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{resume_id}", response_model=ResumeVersionResponse)
async def get_resume_version(
    resume_id: UUID,
    user: User = Depends(get_current_user),
    repository: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVersionResponse:
    resume = await GetResumeVersionUseCase(repository).execute(
        GetResumeVersionQuery(owner_id=user.id, resume_id=resume_id)
    )
    return ResumeVersionResponse.from_domain(resume)
