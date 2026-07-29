"""Opportunity 应用层依赖的 Repository 契约。"""

from typing import Protocol
from uuid import UUID

from nora.domain.opportunity import JobPosting


class JobPostingRepository(Protocol):
    """用户范围内岗位快照的创建与读取端口。"""

    async def add(self, job_posting: JobPosting) -> JobPosting: ...

    async def get_by_id(self, job_posting_id: UUID) -> JobPosting | None: ...

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[JobPosting]: ...

    async def commit(self) -> None: ...
