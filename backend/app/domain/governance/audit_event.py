"""不可变审计事件及其领域规则。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_AUDIT_SUMMARY_LENGTH = 2_000
MAX_TARGET_TYPE_LENGTH = 100
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class AuditAction(StrEnum):
    """审计事件支持的业务动作。"""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """只追加、不可修改的业务审计事实。"""

    id: UUID
    actor_id: UUID
    action: AuditAction
    target_type: str
    target_id: UUID
    target_version: int
    before_summary: str | None
    after_summary: str | None
    occurred_at: datetime
    idempotency_key: str | None

    @classmethod
    def create(
        cls,
        *,
        actor_id: UUID,
        action: AuditAction,
        target_type: str,
        target_id: UUID,
        target_version: int,
        before_summary: str | None = None,
        after_summary: str | None = None,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> "AuditEvent":
        """规范化审计摘要并创建 UTC 事件。"""

        if not isinstance(action, AuditAction):
            raise DomainError("Audit action is invalid", error_code=ErrorCode.INVALID_AUDIT_ACTION)
        normalized_target_type = _normalize_required_text(
            target_type,
            max_length=MAX_TARGET_TYPE_LENGTH,
            error_code=ErrorCode.INVALID_AUDIT_TARGET_TYPE,
        )
        normalized_key = _normalize_optional_text(
            idempotency_key,
            max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
            error_code=ErrorCode.INVALID_AUDIT_IDEMPOTENCY_KEY,
        )
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise DomainError(
                "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
            )
        if (
            isinstance(target_version, bool)
            or not isinstance(target_version, int)
            or target_version < 1
        ):
            raise DomainError(
                "Target version must be a positive integer",
                error_code=ErrorCode.INVALID_AUDIT_TARGET_VERSION,
            )

        return cls(
            id=uuid4(),
            actor_id=actor_id,
            action=action,
            target_type=normalized_target_type,
            target_id=target_id,
            target_version=target_version,
            before_summary=_normalize_optional_text(
                before_summary,
                max_length=MAX_AUDIT_SUMMARY_LENGTH,
                error_code=ErrorCode.INVALID_AUDIT_SUMMARY,
            ),
            after_summary=_normalize_optional_text(
                after_summary,
                max_length=MAX_AUDIT_SUMMARY_LENGTH,
                error_code=ErrorCode.INVALID_AUDIT_SUMMARY,
            ),
            occurred_at=timestamp.astimezone(timezone.utc),
            idempotency_key=normalized_key,
        )

    def to_dict(self) -> dict[str, Any]:
        """返回可稳定序列化且不含可变对象的公开表示。"""

        return {
            "id": str(self.id),
            "actor_id": str(self.actor_id),
            "action": self.action.value,
            "target_type": self.target_type,
            "target_id": str(self.target_id),
            "target_version": self.target_version,
            "before_summary": self.before_summary,
            "after_summary": self.after_summary,
            "occurred_at": self.occurred_at.isoformat(),
            "idempotency_key": self.idempotency_key,
        }


def _normalize_required_text(value: str, *, max_length: int, error_code: ErrorCode) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > max_length:
        raise DomainError("Audit text is invalid", error_code=error_code)
    return normalized


def _normalize_optional_text(
    value: str | None,
    *,
    max_length: int,
    error_code: ErrorCode,
) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise DomainError("Audit text is invalid", error_code=error_code)
    return normalized
