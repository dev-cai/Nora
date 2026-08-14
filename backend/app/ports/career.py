"""Career Profile 应用层依赖的 Repository 契约。"""

from typing import Protocol
from uuid import UUID

from app.domain.career import CandidateProfile, ResumeVersion


class CandidateProfileRepository(Protocol):
    """用户范围内的 CandidateProfile 版本仓库。"""

    async def get_latest(self) -> CandidateProfile | None: ...

    async def get_version(self, version: int) -> CandidateProfile | None: ...

    async def add(self, profile: CandidateProfile) -> CandidateProfile: ...

    async def commit(self) -> None: ...


class ResumeVersionRepository(Protocol):
    """用户范围内的不可变 ResumeVersion 仓库。"""

    async def publish(self, profile: CandidateProfile, title: str) -> ResumeVersion: ...

    async def get_by_id(self, resume_id: UUID) -> ResumeVersion | None: ...

    async def get_by_identity(self, resume_id: UUID, version: int) -> ResumeVersion | None: ...

    async def list(self, *, offset: int, limit: int) -> list[ResumeVersion]: ...

    async def count(self) -> int: ...

    async def commit(self) -> None: ...
