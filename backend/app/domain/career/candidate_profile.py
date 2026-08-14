"""用户确认事实主档及字段级确认规则。"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode


class ConfirmationStatus(StrEnum):
    """主档字段的确认状态。"""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ProfileSourceType(StrEnum):
    """M2 支持的主档事实来源。"""

    USER_INPUT = "user_input"


_ALLOWED_TRANSITIONS = {
    ConfirmationStatus.UNCONFIRMED: frozenset(ConfirmationStatus),
    ConfirmationStatus.CONFIRMED: frozenset(ConfirmationStatus),
    ConfirmationStatus.REJECTED: frozenset(ConfirmationStatus),
    ConfirmationStatus.SUPERSEDED: frozenset({ConfirmationStatus.SUPERSEDED}),
}
_MISSING = object()


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    """用户范围内、按更新追加版本的不可变主档快照。"""

    id: UUID
    owner_id: UUID
    version: int
    _content_json: str
    created_at: datetime
    updated_at: datetime

    @property
    def content(self) -> dict[str, Any]:
        """返回可安全修改的主档内容副本。"""

        return json.loads(self._content_json)

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        content: dict[str, Any],
        now: datetime | None = None,
    ) -> "CandidateProfile":
        """创建主档首个版本。"""

        timestamp = _utc_timestamp(now)
        enriched = _enrich_facts(content, timestamp)
        _fact_path_items(enriched)
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            version=1,
            _content_json=_canonical_content(enriched),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def next_version(
        self,
        *,
        content: dict[str, Any],
        now: datetime | None = None,
    ) -> "CandidateProfile":
        """校验字段状态转换并创建后继快照。"""

        timestamp = _utc_timestamp(now)
        enriched = _enrich_facts(content, timestamp)
        previous = self.content
        _validate_transitions(previous, enriched)
        _preserve_unchanged_timestamps(previous, enriched)
        return CandidateProfile(
            id=self.id,
            owner_id=self.owner_id,
            version=self.version + 1,
            _content_json=_canonical_content(enriched),
            created_at=self.created_at,
            updated_at=timestamp,
        )

    @classmethod
    def restore(
        cls,
        *,
        profile_id: UUID,
        owner_id: UUID,
        version: int,
        content: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> "CandidateProfile":
        """从可信持久化记录恢复主档快照。"""

        if version < 1:
            raise DomainError(
                "Profile version must be positive", error_code=ErrorCode.INVALID_PROFILE_VERSION
            )
        return cls(
            id=profile_id,
            owner_id=owner_id,
            version=version,
            _content_json=_canonical_content(content),
            created_at=_utc_timestamp(created_at),
            updated_at=_utc_timestamp(updated_at),
        )

    def confirmed_data(self) -> dict[str, Any]:
        """返回供后续规则使用的 confirmed-only 数据。"""

        filtered = _filter_confirmed(self.content)
        return filtered if isinstance(filtered, dict) else {}


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return timestamp.astimezone(timezone.utc)


def _canonical_content(content: dict[str, Any]) -> str:
    try:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Profile content must be JSON serializable", error_code=ErrorCode.INVALID_PROFILE
        ) from exc


def _enrich_facts(value: Any, timestamp: datetime) -> Any:
    if isinstance(value, dict):
        if "value" in value and "confirmation_status" in value:
            try:
                status = ConfirmationStatus(value["confirmation_status"])
                source_type = ProfileSourceType(
                    value.get("source_type", ProfileSourceType.USER_INPUT)
                )
            except (TypeError, ValueError) as exc:
                raise DomainError(
                    "Profile field status or source is invalid",
                    error_code=ErrorCode.INVALID_PROFILE_FIELD,
                ) from exc
            return {
                "value": value["value"],
                "confirmation_status": status.value,
                "source_type": source_type.value,
                "updated_at": timestamp.isoformat(),
            }
        return {key: _enrich_facts(item, timestamp) for key, item in value.items()}
    if isinstance(value, list):
        return [_enrich_facts(item, timestamp) for item in value]
    return value


def _fact_path_items(
    value: Any, path: tuple[str, ...] = ()
) -> dict[tuple[str, ...], dict[str, Any]]:
    if isinstance(value, dict):
        if "value" in value and "confirmation_status" in value:
            return {path: value}
        result: dict[tuple[str, ...], dict[str, Any]] = {}
        for key, item in value.items():
            result.update(_fact_path_items(item, (*path, key)))
        return result
    if isinstance(value, list):
        result = {}
        identifiers: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, dict) or "id" not in item:
                raise DomainError(
                    f"Profile collection item at index {index} must have an id",
                    error_code=ErrorCode.INVALID_PROFILE_ITEM_ID,
                )
            identifier = str(item["id"])
            if identifier in identifiers:
                raise DomainError(
                    "Profile collection item ids must be unique",
                    error_code=ErrorCode.INVALID_PROFILE_ITEM_ID,
                )
            identifiers.add(identifier)
            result.update(_fact_path_items(item, (*path, identifier)))
        return result
    return {}


def _validate_transitions(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_facts = _fact_path_items(previous)
    current_facts = _fact_path_items(current)
    for path, current_fact in current_facts.items():
        previous_fact = previous_facts.get(path)
        if previous_fact is None:
            continue
        previous_status = ConfirmationStatus(previous_fact["confirmation_status"])
        current_status = ConfirmationStatus(current_fact["confirmation_status"])
        if current_status not in _ALLOWED_TRANSITIONS[previous_status]:
            raise DomainError(
                f"Confirmation status cannot transition from {previous_status} to {current_status}",
                error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION,
            )


def _preserve_unchanged_timestamps(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_facts = _fact_path_items(previous)
    current_facts = _fact_path_items(current)
    compared_keys = ("value", "confirmation_status", "source_type")
    for path, current_fact in current_facts.items():
        previous_fact = previous_facts.get(path)
        if previous_fact is not None and all(
            current_fact.get(key) == previous_fact.get(key) for key in compared_keys
        ):
            current_fact["updated_at"] = previous_fact["updated_at"]


def _filter_confirmed(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value and "confirmation_status" in value:
            if value["confirmation_status"] == ConfirmationStatus.CONFIRMED:
                return value["value"]
            return _MISSING
        filtered = {
            key: item
            for key, nested in value.items()
            if (item := _filter_confirmed(nested)) is not _MISSING
        }
        return filtered
    if isinstance(value, list):
        items = [item for nested in value if (item := _filter_confirmed(nested)) is not _MISSING]
        return items
    return value
