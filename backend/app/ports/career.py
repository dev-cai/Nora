"""Career Profile 应用层依赖的 Repository 契约。"""

from typing import Protocol

from app.domain.career import CandidateProfile


class CandidateProfileRepository(Protocol):
    """用户范围内的 CandidateProfile 版本仓库。"""

    async def get_latest(self) -> CandidateProfile | None: ...

    async def get_version(self, version: int) -> CandidateProfile | None: ...

    async def add(self, profile: CandidateProfile) -> CandidateProfile: ...

    async def commit(self) -> None: ...
