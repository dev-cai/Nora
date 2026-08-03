"""ResumeVersion 发布、读取与分页用例。"""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError
from app.domain.career import ResumeVersion
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository


@dataclass(frozen=True, slots=True)
class PublishResumeVersionCommand:
    owner_id: UUID
    profile_version: int
    title: str


@dataclass(frozen=True, slots=True)
class GetResumeVersionQuery:
    owner_id: UUID
    resume_id: UUID


@dataclass(frozen=True, slots=True)
class ListResumeVersionsQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListResumeVersionsResult:
    items: tuple[ResumeVersion, ...]
    page: int
    page_size: int
    total: int


class PublishResumeVersionUseCase:
    """从用户指定的 CandidateProfile 版本发布简历快照。"""

    def __init__(
        self,
        profile_repository: CandidateProfileRepository,
        resume_repository: ResumeVersionRepository,
    ) -> None:
        self.profile_repository = profile_repository
        self.resume_repository = resume_repository

    async def execute(self, command: PublishResumeVersionCommand) -> ResumeVersion:
        if command.profile_version < 1:
            raise ApplicationError(
                "Profile version must be positive", error_code="invalid_profile_version"
            )
        profile = await self.profile_repository.get_version(command.profile_version)
        if profile is None or profile.owner_id != command.owner_id:
            raise ApplicationError("Candidate profile not found", error_code="entity_not_found")
        resume = await self.resume_repository.publish(profile, command.title)
        await self.resume_repository.commit()
        return resume


class GetResumeVersionUseCase:
    """读取当前认证用户拥有的历史简历版本。"""

    def __init__(self, repository: ResumeVersionRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetResumeVersionQuery) -> ResumeVersion:
        resume = await self.repository.get_by_id(query.resume_id)
        if resume is None or resume.owner_id != query.owner_id:
            raise ApplicationError("Resume version not found", error_code="entity_not_found")
        return resume


class ListResumeVersionsUseCase:
    """按发布顺序倒序分页读取当前用户的简历版本。"""

    def __init__(self, repository: ResumeVersionRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListResumeVersionsQuery) -> ListResumeVersionsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError(
                "Page must be at least 1 and page_size must be between 1 and 100",
                error_code="invalid_pagination",
            )
        items = await self.repository.list(
            offset=(query.page - 1) * query.page_size,
            limit=query.page_size,
        )
        return ListResumeVersionsResult(
            items=tuple(items),
            page=query.page,
            page_size=query.page_size,
            total=await self.repository.count(),
        )
