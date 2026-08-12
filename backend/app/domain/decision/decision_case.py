"""不可变决策输入案例及其生命周期规则。"""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError

MAX_RULE_SET_VERSION_LENGTH = 100
MAX_FAILURE_CODE_LENGTH = 100
MAX_FAILURE_MESSAGE_LENGTH = 1_000


class DecisionCaseStatus(StrEnum):
    """DecisionCase 的持久化生命周期。"""

    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DecisionCase:
    """固定全部决策输入版本的不可变案例。"""

    id: UUID
    owner_id: UUID
    job_posting_id: UUID
    job_posting_version: int
    job_requirement_snapshot_id: UUID
    job_requirement_snapshot_version: int
    candidate_profile_id: UUID
    candidate_profile_version: int
    resume_version_id: UUID
    resume_version: int
    rule_set_version: str
    input_fingerprint: str
    status: DecisionCaseStatus
    created_at: datetime
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        job_requirement_snapshot_id: UUID,
        job_requirement_snapshot_version: int,
        candidate_profile_id: UUID,
        candidate_profile_version: int,
        resume_version_id: UUID,
        resume_version: int,
        rule_set_version: str,
        now: datetime | None = None,
    ) -> "DecisionCase":
        """规范化并固定一次确定性决策的完整输入。"""

        versions = {
            "job_posting_version": _positive_version(job_posting_version),
            "job_requirement_snapshot_version": _positive_version(job_requirement_snapshot_version),
            "candidate_profile_version": _positive_version(candidate_profile_version),
            "resume_version": _positive_version(resume_version),
        }
        normalized_rule_set = _normalize_rule_set_version(rule_set_version)
        fingerprint = _input_fingerprint(
            job_posting_id=job_posting_id,
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            candidate_profile_id=candidate_profile_id,
            resume_version_id=resume_version_id,
            rule_set_version=normalized_rule_set,
            **versions,
        )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            job_posting_id=job_posting_id,
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            candidate_profile_id=candidate_profile_id,
            resume_version_id=resume_version_id,
            rule_set_version=normalized_rule_set,
            input_fingerprint=fingerprint,
            status=DecisionCaseStatus.CREATED,
            created_at=_utc_timestamp(now),
            completed_at=None,
            failure_code=None,
            failure_message=None,
            **versions,
        )

    @classmethod
    def restore(
        cls,
        *,
        case_id: UUID,
        owner_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        job_requirement_snapshot_id: UUID,
        job_requirement_snapshot_version: int,
        candidate_profile_id: UUID,
        candidate_profile_version: int,
        resume_version_id: UUID,
        resume_version: int,
        rule_set_version: str,
        input_fingerprint: str,
        status: DecisionCaseStatus,
        created_at: datetime,
        completed_at: datetime | None,
        failure_code: str | None,
        failure_message: str | None,
    ) -> "DecisionCase":
        """从可信持久化记录恢复案例，并校验领域状态。"""

        case = cls(
            id=case_id,
            owner_id=owner_id,
            job_posting_id=job_posting_id,
            job_posting_version=_positive_version(job_posting_version),
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            job_requirement_snapshot_version=_positive_version(job_requirement_snapshot_version),
            candidate_profile_id=candidate_profile_id,
            candidate_profile_version=_positive_version(candidate_profile_version),
            resume_version_id=resume_version_id,
            resume_version=_positive_version(resume_version),
            rule_set_version=_normalize_rule_set_version(rule_set_version),
            input_fingerprint=_normalize_fingerprint(input_fingerprint),
            status=_status(status),
            created_at=_utc_timestamp(created_at),
            completed_at=None if completed_at is None else _utc_timestamp(completed_at),
            failure_code=failure_code,
            failure_message=failure_message,
        )
        case._validate_state()
        return case

    def complete(self, *, now: datetime | None = None) -> "DecisionCase":
        """把新建案例标记为已完成。"""

        self._require_created()
        return replace(
            self,
            status=DecisionCaseStatus.COMPLETED,
            completed_at=_utc_timestamp(now),
        )

    def fail(
        self,
        *,
        failure_code: str,
        failure_message: str,
        now: datetime | None = None,
    ) -> "DecisionCase":
        """把新建案例标记为失败并保存稳定错误信息。"""

        self._require_created()
        code = _normalize_text(failure_code, MAX_FAILURE_CODE_LENGTH, "invalid_failure_code")
        message = _normalize_text(
            failure_message, MAX_FAILURE_MESSAGE_LENGTH, "invalid_failure_message"
        )
        return replace(
            self,
            status=DecisionCaseStatus.FAILED,
            completed_at=_utc_timestamp(now),
            failure_code=code,
            failure_message=message,
        )

    def _require_created(self) -> None:
        if self.status is not DecisionCaseStatus.CREATED:
            raise DomainError(
                "Decision case has already finished", error_code="invalid_decision_case_state"
            )

    def _validate_state(self) -> None:
        is_created = (
            self.status is DecisionCaseStatus.CREATED
            and self.completed_at is None
            and self.failure_code is None
            and self.failure_message is None
        )
        is_completed = (
            self.status is DecisionCaseStatus.COMPLETED
            and self.completed_at is not None
            and self.failure_code is None
            and self.failure_message is None
        )
        is_failed = (
            self.status is DecisionCaseStatus.FAILED
            and self.completed_at is not None
            and self.failure_code is not None
            and self.failure_message is not None
        )
        if not (is_created or is_completed or is_failed):
            raise DomainError(
                "Decision case state is inconsistent", error_code="invalid_decision_case_state"
            )


def _positive_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Input version must be positive", error_code="invalid_version")
    return value


def _normalize_rule_set_version(value: str) -> str:
    return _normalize_text(value, MAX_RULE_SET_VERSION_LENGTH, "invalid_rule_set_version")


def _normalize_text(value: str, maximum: int, error_code: str) -> str:
    if not isinstance(value, str):
        raise DomainError("Value must be a string", error_code=error_code)
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise DomainError(f"Value must contain 1-{maximum} characters", error_code=error_code)
    return normalized


def _normalize_fingerprint(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise DomainError("Input fingerprint is invalid", error_code="invalid_input_fingerprint")
    return normalized


def _status(value: DecisionCaseStatus) -> DecisionCaseStatus:
    try:
        return DecisionCaseStatus(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Decision case status is invalid", error_code="invalid_decision_case_state"
        ) from exc


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return timestamp.astimezone(timezone.utc)


def _input_fingerprint(**values: UUID | int | str) -> str:
    canonical = json.dumps(
        {key: str(value) if isinstance(value, UUID) else value for key, value in values.items()},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
