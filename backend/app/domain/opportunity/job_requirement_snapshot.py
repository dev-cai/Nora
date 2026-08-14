"""用户确认的结构化岗位要求快照及其版本规则。"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, TypeVar
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_SKILL_NAME_LENGTH = 100
MAX_SKILL_COUNT = 50
MAX_SOURCE_RANGE_LENGTH = 64
MAX_TEXT_VALUE_LENGTH = 200
_REQUIRED_FIELDS = (
    "required_skills",
    "minimum_experience_years",
    "degree_requirement",
    "location_requirement",
    "work_mode",
)
_MISSING = object()


class WorkMode(StrEnum):
    """岗位要求的工作方式。"""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class RequirementConfirmationStatus(StrEnum):
    """岗位要求字段的确认状态。"""

    UNKNOWN = "unknown"
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class RequirementSourceType(StrEnum):
    """岗位要求字段的来源定位方式。"""

    MANUAL = "manual"
    TEXT_RANGE = "text_range"
    OCR_PREVIEW = "ocr_preview"


@dataclass(frozen=True, slots=True)
class JobRequirementSnapshot:
    """用户范围内、按岗位追加版本的结构化岗位要求快照。

    每个版本是不可变记录：修改确认结果必须创建新版本，不覆盖历史快照。
    """

    id: UUID
    owner_id: UUID
    version: int
    job_posting_id: UUID
    job_posting_version: int
    _content_json: str
    created_at: datetime
    updated_at: datetime

    @property
    def content(self) -> dict[str, Any]:
        """返回可安全修改的岗位要求内容副本。"""

        return json.loads(self._content_json)

    @property
    def content_hash(self) -> str:
        """内容哈希，用于幂等重放与等价标识。"""

        return _content_hash(self._content_json)

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        content: dict[str, Any],
        now: datetime | None = None,
    ) -> "JobRequirementSnapshot":
        """创建岗位要求的首个版本。"""

        timestamp = _utc_timestamp(now)
        normalized = _normalize_content(content)
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            version=1,
            job_posting_id=job_posting_id,
            job_posting_version=_positive_int(
                job_posting_version, "Job posting version must be positive"
            ),
            _content_json=_canonical_content(normalized),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def next_version(
        self,
        *,
        content: dict[str, Any],
        now: datetime | None = None,
    ) -> "JobRequirementSnapshot":
        """基于当前快照创建下一个版本，保持岗位引用与历史创建时间。"""

        timestamp = _utc_timestamp(now)
        normalized = _normalize_content(content)
        return JobRequirementSnapshot(
            id=self.id,
            owner_id=self.owner_id,
            version=self.version + 1,
            job_posting_id=self.job_posting_id,
            job_posting_version=self.job_posting_version,
            _content_json=_canonical_content(normalized),
            created_at=self.created_at,
            updated_at=timestamp,
        )

    @classmethod
    def restore(
        cls,
        *,
        snapshot_id: UUID,
        owner_id: UUID,
        version: int,
        job_posting_id: UUID,
        job_posting_version: int,
        content: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> "JobRequirementSnapshot":
        """从可信持久化记录恢复岗位要求快照版本。"""

        return cls(
            id=snapshot_id,
            owner_id=owner_id,
            version=_positive_int(version, "Snapshot version must be positive"),
            job_posting_id=job_posting_id,
            job_posting_version=_positive_int(
                job_posting_version, "Job posting version must be positive"
            ),
            _content_json=_canonical_content(content),
            created_at=_utc_timestamp(created_at),
            updated_at=_utc_timestamp(updated_at),
        )

    def confirmed_requirements(self) -> dict[str, Any]:
        """返回供后续确定性规则使用的 confirmed-only 内容。"""

        filtered = _filter_confirmed(self.content)
        return filtered if isinstance(filtered, dict) else {}


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return timestamp.astimezone(timezone.utc)


def _positive_int(value: int, message: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise DomainError(message, error_code=ErrorCode.INVALID_VERSION)
    return value


def _canonical_content(content: dict[str, Any]) -> str:
    try:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Requirement content must be JSON serializable",
            error_code=ErrorCode.INVALID_REQUIREMENT,
        ) from exc


def _content_hash(canonical: str) -> str:
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_content(content: dict[str, Any]) -> dict[str, Any]:
    """校验五个字段的事实结构并返回规范化的内容字典。"""

    if not isinstance(content, dict):
        raise DomainError(
            "Requirement content must be an object", error_code=ErrorCode.INVALID_REQUIREMENT
        )
    missing = [field for field in _REQUIRED_FIELDS if field not in content]
    if missing:
        raise DomainError(
            f"Requirement content is missing fields: {', '.join(missing)}",
            error_code=ErrorCode.INVALID_REQUIREMENT,
        )

    normalized: dict[str, Any] = {}
    for field in _REQUIRED_FIELDS:
        fact = content[field]
        if not isinstance(fact, dict):
            raise DomainError(
                f"Requirement field {field} must be an object",
                error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
            )
        normalized[field] = _normalize_fact(field, fact)
    return normalized


def _normalize_fact(field: str, fact: dict[str, Any]) -> dict[str, Any]:
    status = _enum_or_error(
        RequirementConfirmationStatus,
        fact.get("confirmation_status"),
        ErrorCode.INVALID_CONFIRMATION_STATUS,
    )
    source_type = _enum_or_error(
        RequirementSourceType,
        fact.get("source_type"),
        ErrorCode.INVALID_SOURCE_TYPE,
    )
    source_range = fact.get("source_range")
    if source_range is not None:
        if not isinstance(source_range, str) or not source_range.strip():
            raise DomainError(
                "Source range must be a non-empty string", error_code=ErrorCode.INVALID_SOURCE_RANGE
            )
        if len(source_range) > MAX_SOURCE_RANGE_LENGTH:
            raise DomainError(
                f"Source range cannot exceed {MAX_SOURCE_RANGE_LENGTH} characters",
                error_code=ErrorCode.INVALID_SOURCE_RANGE,
            )
        source_range = source_range.strip()

    value = _normalize_field_value(field, fact.get("value"), status)
    return {
        "value": value,
        "confirmation_status": status.value,
        "source_type": source_type.value,
        "source_range": source_range,
    }


def _normalize_field_value(field: str, value: Any, status: RequirementConfirmationStatus) -> Any:
    if status is RequirementConfirmationStatus.UNKNOWN:
        if value is not None and value != []:
            raise DomainError(
                f"Unknown field {field} must not carry a value",
                error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
            )
        return None
    if value is None:
        raise DomainError(
            f"Field {field} requires a value when not unknown",
            error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
        )

    if field == "required_skills":
        return _normalize_skills(value)
    if field == "minimum_experience_years":
        return _normalize_experience_years(value)
    if field == "work_mode":
        return _normalize_work_mode(value).value
    return _normalize_text(value, field)


def _normalize_skills(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise DomainError(
            "required_skills must be a list", error_code=ErrorCode.INVALID_REQUIREMENT_FIELD
        )
    if len(value) > MAX_SKILL_COUNT:
        raise DomainError(
            f"required_skills cannot exceed {MAX_SKILL_COUNT} items",
            error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DomainError(
                "required_skills items must be non-empty strings",
                error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
            )
        collapsed = " ".join(item.split())
        if len(collapsed) > MAX_SKILL_NAME_LENGTH:
            raise DomainError(
                f"Skill name cannot exceed {MAX_SKILL_NAME_LENGTH} characters",
                error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
            )
        normalized.append(collapsed)
    return normalized


def _normalize_experience_years(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainError(
            "minimum_experience_years must be a non-negative integer",
            error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
        )
    return value


def _normalize_work_mode(value: Any) -> WorkMode:
    if isinstance(value, WorkMode):
        return value
    try:
        return WorkMode(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "work_mode must be one of onsite, hybrid, remote or unknown",
            error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
        ) from exc


def _normalize_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(
            f"{field} must be a non-empty string", error_code=ErrorCode.INVALID_REQUIREMENT_FIELD
        )
    collapsed = " ".join(value.split())
    if len(collapsed) > MAX_TEXT_VALUE_LENGTH:
        raise DomainError(
            f"{field} cannot exceed {MAX_TEXT_VALUE_LENGTH} characters",
            error_code=ErrorCode.INVALID_REQUIREMENT_FIELD,
        )
    return collapsed


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _enum_or_error(enum_type: type[_EnumT], value: Any, error_code: ErrorCode) -> _EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(f"{enum_type.__name__} is invalid", error_code=error_code) from exc


def _filter_confirmed(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value and "confirmation_status" in value:
            if value["confirmation_status"] == RequirementConfirmationStatus.CONFIRMED:
                return value["value"]
            return _MISSING
        filtered = {
            key: item
            for key, nested in value.items()
            if (item := _filter_confirmed(nested)) is not _MISSING
        }
        return filtered
    return value
