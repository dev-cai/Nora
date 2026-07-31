"""Opportunity 应用层依赖的 Repository 契约。"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.opportunity import JobPosting


@dataclass(frozen=True, slots=True)
class StoredIdempotentJobPosting:
    """幂等键对应的首次岗位快照和规范化请求指纹。"""

    job_posting: JobPosting
    request_fingerprint: str


class JobPostingRepository(Protocol):
    """用户范围内岗位快照的创建与读取端口。"""

    async def add(self, job_posting: JobPosting) -> JobPosting: ...

    async def add_idempotent(
        self,
        job_posting: JobPosting,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JobPosting: ...

    async def get_by_id(self, job_posting_id: UUID) -> JobPosting | None: ...

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> StoredIdempotentJobPosting | None: ...

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[JobPosting]: ...

    async def commit(self) -> None: ...
