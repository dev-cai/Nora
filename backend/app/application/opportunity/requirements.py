"""岗位要求快照的保存、读取与分页用例。"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.opportunity import JobRequirementSnapshot
from app.ports.opportunity import JobPostingRepository, JobRequirementSnapshotRepository


@dataclass(frozen=True, slots=True)
class SaveJobRequirementSnapshotCommand:
    """保存当前用户岗位的结构化要求，相同内容幂等重放。"""

    owner_id: UUID
    job_posting_id: UUID
    job_posting_version: int
    content: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SaveJobRequirementSnapshotResult:
    """保存结果及是否命中已有同内容快照。"""

    snapshot: JobRequirementSnapshot
    replayed: bool


@dataclass(frozen=True, slots=True)
class GetJobRequirementSnapshotQuery:
    """读取当前用户岗位的指定版本或最新版本。"""

    owner_id: UUID
    job_posting_id: UUID
    version: int | None = None


@dataclass(frozen=True, slots=True)
class ListJobRequirementSnapshotsQuery:
    """按岗位分页读取岗位要求快照版本。"""

    owner_id: UUID
    job_posting_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListJobRequirementSnapshotsResult:
    """稳定分页的岗位要求快照及总数。"""

    items: tuple[JobRequirementSnapshot, ...]
    page: int
    page_size: int
    total: int


class SaveJobRequirementSnapshotUseCase:
    """创建岗位要求首个版本，或基于最新版本追加新版本，相同内容幂等重放。"""

    def __init__(
        self,
        repository: JobRequirementSnapshotRepository,
        posting_repository: JobPostingRepository,
    ) -> None:
        self.repository = repository
        self.posting_repository = posting_repository

    async def execute(
        self, command: SaveJobRequirementSnapshotCommand
    ) -> SaveJobRequirementSnapshotResult:
        posting = await self.posting_repository.get_by_id(command.job_posting_id)
        if posting is None or posting.owner_id != command.owner_id:
            raise ApplicationError("Job posting not found", error_code=ErrorCode.ENTITY_NOT_FOUND)

        latest = await self.repository.get_latest(command.job_posting_id)
        candidate = self._build_version(latest, command)
        if latest is not None and latest.content_hash == candidate.content_hash:
            return SaveJobRequirementSnapshotResult(snapshot=latest, replayed=True)

        try:
            stored = await self.repository.add(candidate)
            await self.repository.commit()
        except InfrastructureError as exc:
            if exc.error_code is not ErrorCode.JOB_REQUIREMENT_VERSION_CONFLICT:
                raise
            raise InfrastructureError(
                "Job requirement snapshot version conflict",
                error_code=ErrorCode.JOB_REQUIREMENT_VERSION_CONFLICT,
            ) from exc
        return SaveJobRequirementSnapshotResult(snapshot=stored, replayed=False)

    @staticmethod
    def _build_version(
        latest: JobRequirementSnapshot | None,
        command: SaveJobRequirementSnapshotCommand,
    ) -> JobRequirementSnapshot:
        if latest is None:
            return JobRequirementSnapshot.create(
                owner_id=command.owner_id,
                job_posting_id=command.job_posting_id,
                job_posting_version=command.job_posting_version,
                content=command.content,
            )
        return latest.next_version(content=command.content)


class GetJobRequirementSnapshotUseCase:
    """读取当前用户岗位的指定版本或最新版本。"""

    def __init__(self, repository: JobRequirementSnapshotRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetJobRequirementSnapshotQuery) -> JobRequirementSnapshot:
        if query.version is None:
            snapshot = await self.repository.get_latest(query.job_posting_id)
        else:
            snapshot = await self.repository.get_version(query.job_posting_id, query.version)
        if snapshot is None or snapshot.owner_id != query.owner_id:
            raise ApplicationError(
                "Job requirement snapshot not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return snapshot


class ListJobRequirementSnapshotsUseCase:
    """按创建时间倒序返回岗位要求快照版本。"""

    def __init__(self, repository: JobRequirementSnapshotRepository) -> None:
        self.repository = repository

    async def execute(
        self, query: ListJobRequirementSnapshotsQuery
    ) -> ListJobRequirementSnapshotsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError(
                "Page must be at least 1 and page_size must be between 1 and 100",
                error_code=ErrorCode.INVALID_PAGINATION,
            )
        offset = (query.page - 1) * query.page_size
        items = await self.repository.list(
            query.job_posting_id, offset=offset, limit=query.page_size
        )
        total = await self.repository.count(query.job_posting_id)
        return ListJobRequirementSnapshotsResult(
            items=tuple(items),
            page=query.page,
            page_size=query.page_size,
            total=total,
        )
