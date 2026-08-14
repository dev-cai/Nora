"""CandidateProfile 创建、更新、历史读取与 confirmed-only 策略。"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.career import CandidateProfile
from app.ports.career import CandidateProfileRepository


@dataclass(frozen=True, slots=True)
class PutCandidateProfileCommand:
    """替换当前用户主档内容并追加版本。"""

    owner_id: UUID
    content: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GetCandidateProfileQuery:
    """读取当前用户的最新或指定主档版本。"""

    owner_id: UUID
    version: int | None = None


class PutCandidateProfileUseCase:
    """保存一个完整主档快照。"""

    def __init__(self, repository: CandidateProfileRepository) -> None:
        self.repository = repository

    async def execute(self, command: PutCandidateProfileCommand) -> CandidateProfile:
        current = await self.repository.get_latest()
        if current is None:
            profile = CandidateProfile.create(owner_id=command.owner_id, content=command.content)
        else:
            if current.owner_id != command.owner_id:
                raise ApplicationError(
                    "Candidate profile not found", error_code=ErrorCode.ENTITY_NOT_FOUND
                )
            profile = current.next_version(content=command.content)
        stored = await self.repository.add(profile)
        await self.repository.commit()
        return stored


class GetCandidateProfileUseCase:
    """按用户范围读取主档版本。"""

    def __init__(self, repository: CandidateProfileRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetCandidateProfileQuery) -> CandidateProfile:
        if query.version is not None and query.version < 1:
            raise ApplicationError(
                "Profile version must be positive", error_code=ErrorCode.INVALID_PROFILE_VERSION
            )
        profile = (
            await self.repository.get_latest()
            if query.version is None
            else await self.repository.get_version(query.version)
        )
        if profile is None or profile.owner_id != query.owner_id:
            raise ApplicationError(
                "Candidate profile not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return profile


def confirmed_profile_data(profile: CandidateProfile) -> dict[str, Any]:
    """为 M3 规则提供唯一的 confirmed-only 主档视图。"""

    return profile.confirmed_data()
