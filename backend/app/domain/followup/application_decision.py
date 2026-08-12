"""Immutable apply/skip decision bound to one report version."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError

MAX_DECISION_REASON_LENGTH = 1_000
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class ApplicationDecisionStatus(StrEnum):
    """The two explicit outcomes available after analysis."""

    APPLY = "apply"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class ApplicationDecision:
    """One immutable user decision for an immutable report."""

    id: UUID
    owner_id: UUID
    actor_id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    resume_version_id: UUID
    resume_version: int
    status: ApplicationDecisionStatus
    reason: str | None
    idempotency_key: str
    request_fingerprint: str
    decided_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        actor_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        resume_version_id: UUID,
        resume_version: int,
        status: ApplicationDecisionStatus,
        reason: str | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "ApplicationDecision":
        normalized_status = _status(status)
        normalized_reason = _reason(
            reason,
            required=normalized_status is ApplicationDecisionStatus.SKIP,
        )
        normalized_key = _required_text(
            idempotency_key,
            MAX_IDEMPOTENCY_KEY_LENGTH,
            "invalid_idempotency_key",
        )
        report_version = _positive_version(report_version)
        resume_version = _positive_version(resume_version)
        fingerprint = _request_fingerprint(
            report_id=report_id,
            report_version=report_version,
            status=normalized_status,
            reason=normalized_reason,
        )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            actor_id=actor_id,
            report_id=report_id,
            report_version=report_version,
            decision_case_id=decision_case_id,
            resume_version_id=resume_version_id,
            resume_version=resume_version,
            status=normalized_status,
            reason=normalized_reason,
            idempotency_key=normalized_key,
            request_fingerprint=fingerprint,
            decided_at=_utc_timestamp(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        decision_id: UUID,
        owner_id: UUID,
        actor_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        resume_version_id: UUID,
        resume_version: int,
        status: ApplicationDecisionStatus,
        reason: str | None,
        idempotency_key: str,
        request_fingerprint: str,
        decided_at: datetime,
    ) -> "ApplicationDecision":
        restored = cls.create(
            owner_id=owner_id,
            actor_id=actor_id,
            report_id=report_id,
            report_version=report_version,
            decision_case_id=decision_case_id,
            resume_version_id=resume_version_id,
            resume_version=resume_version,
            status=status,
            reason=reason,
            idempotency_key=idempotency_key,
            now=decided_at,
        )
        if restored.request_fingerprint != request_fingerprint:
            raise DomainError(
                "Application decision fingerprint is invalid",
                error_code="invalid_application_decision_fingerprint",
            )
        return cls(
            id=decision_id,
            owner_id=restored.owner_id,
            actor_id=restored.actor_id,
            report_id=restored.report_id,
            report_version=restored.report_version,
            decision_case_id=restored.decision_case_id,
            resume_version_id=restored.resume_version_id,
            resume_version=restored.resume_version,
            status=restored.status,
            reason=restored.reason,
            idempotency_key=restored.idempotency_key,
            request_fingerprint=restored.request_fingerprint,
            decided_at=restored.decided_at,
        )

    def has_same_request(self, other: "ApplicationDecision") -> bool:
        return self.request_fingerprint == other.request_fingerprint


def _status(value: ApplicationDecisionStatus) -> ApplicationDecisionStatus:
    try:
        return ApplicationDecisionStatus(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Application decision status is invalid",
            error_code="invalid_application_decision_status",
        ) from exc


def _reason(value: str | None, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise DomainError("Skip reason is required", error_code="skip_reason_required")
        return None
    if not isinstance(value, str):
        raise DomainError("Decision reason must be text", error_code="invalid_decision_reason")
    normalized = " ".join(value.split())
    if not normalized:
        if required:
            raise DomainError("Skip reason is required", error_code="skip_reason_required")
        return None
    if len(normalized) > MAX_DECISION_REASON_LENGTH:
        raise DomainError(
            "Decision reason is too long", error_code="invalid_decision_reason"
        )
    return normalized


def _required_text(value: str, maximum: int, error_code: str) -> str:
    if not isinstance(value, str):
        raise DomainError("Value must be text", error_code=error_code)
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise DomainError(f"Value must contain 1-{maximum} characters", error_code=error_code)
    return normalized


def _positive_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Version must be positive", error_code="invalid_version")
    return value


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return timestamp.astimezone(timezone.utc)


def _request_fingerprint(
    *,
    report_id: UUID,
    report_version: int,
    status: ApplicationDecisionStatus,
    reason: str | None,
) -> str:
    canonical = json.dumps(
        {
            "reason": reason,
            "report_id": str(report_id),
            "report_version": report_version,
            "status": status.value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
