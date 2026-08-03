"""从用户确认主档发布的不可变简历事实版本。"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError
from app.domain.career.candidate_profile import CandidateProfile

MAX_RESUME_TITLE_LENGTH = 200


@dataclass(frozen=True, slots=True)
class ResumeVersion:
    """固定引用主档版本并持有 confirmed-only 内容快照。"""

    id: UUID
    owner_id: UUID
    version: int
    candidate_profile_id: UUID
    profile_version: int
    title: str
    _content_json: str
    published_at: datetime

    @property
    def content(self) -> dict[str, Any]:
        """返回可安全修改的简历内容副本。"""

        return json.loads(self._content_json)

    @classmethod
    def publish(
        cls,
        *,
        profile: CandidateProfile,
        title: str,
        version: int,
        now: datetime | None = None,
    ) -> "ResumeVersion":
        """从指定主档版本发布 confirmed-only 快照。"""

        normalized_title = _normalize_title(title)
        if version < 1:
            raise DomainError(
                "Resume version must be positive", error_code="invalid_resume_version"
            )
        content = _resume_content(profile.confirmed_data())
        if not content:
            raise DomainError(
                "Candidate profile has no confirmed resume facts",
                error_code="profile_has_no_confirmed_data",
            )
        return cls(
            id=uuid4(),
            owner_id=profile.owner_id,
            version=version,
            candidate_profile_id=profile.id,
            profile_version=profile.version,
            title=normalized_title,
            _content_json=_canonical_content(content),
            published_at=_utc_timestamp(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        resume_id: UUID,
        owner_id: UUID,
        version: int,
        candidate_profile_id: UUID,
        profile_version: int,
        title: str,
        content: dict[str, Any],
        published_at: datetime,
    ) -> "ResumeVersion":
        """从可信持久化记录恢复不可变简历版本。"""

        if version < 1 or profile_version < 1:
            raise DomainError(
                "Resume and profile versions must be positive",
                error_code="invalid_resume_version",
            )
        return cls(
            id=resume_id,
            owner_id=owner_id,
            version=version,
            candidate_profile_id=candidate_profile_id,
            profile_version=profile_version,
            title=_normalize_title(title),
            _content_json=_canonical_content(content),
            published_at=_utc_timestamp(published_at),
        )


def _normalize_title(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_RESUME_TITLE_LENGTH:
        raise DomainError(
            f"Resume title must contain 1-{MAX_RESUME_TITLE_LENGTH} characters",
            error_code="invalid_resume_title",
        )
    return normalized


def _resume_content(confirmed: dict[str, Any]) -> dict[str, Any]:
    content: dict[str, Any] = {}
    basic_information = confirmed.get("basic_information")
    if isinstance(basic_information, dict) and basic_information:
        content["basic_information"] = basic_information

    for section in ("education", "experiences", "skills"):
        items = confirmed.get(section)
        if not isinstance(items, list):
            continue
        meaningful_items = [
            item for item in items if isinstance(item, dict) and any(key != "id" for key in item)
        ]
        if meaningful_items:
            content[section] = meaningful_items
    return content


def _canonical_content(content: dict[str, Any]) -> str:
    try:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Resume content must be JSON serializable", error_code="invalid_resume_content"
        ) from exc


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return timestamp.astimezone(timezone.utc)
