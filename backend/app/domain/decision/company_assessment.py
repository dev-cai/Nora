"""Fixed company intelligence attachment for an immutable decision report."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError


class CompanyAssessmentStatus(StrEnum):
    AVAILABLE = "available"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class CompanyAssessment:
    id: UUID
    owner_id: UUID
    version: int
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    company_snapshot_id: UUID
    company_snapshot_version: int
    status: CompanyAssessmentStatus
    status_reason: str
    generator_version: str
    generation_identity: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        company_snapshot_id: UUID,
        company_snapshot_version: int,
        status: CompanyAssessmentStatus,
        status_reason: str,
        generator_version: str,
        now: datetime | None = None,
    ) -> "CompanyAssessment":
        generator = " ".join(generator_version.split())
        if not generator or len(generator) > 100:
            raise DomainError(
                "Company assessment generator is invalid",
                error_code="invalid_generator_version",
            )
        reason = " ".join(status_reason.split())
        if not reason or len(reason) > 200:
            raise DomainError(
                "Company assessment status reason is invalid",
                error_code="invalid_company_assessment_status",
            )
        report_version_value = _positive(report_version)
        snapshot_version_value = _positive(company_snapshot_version)
        identity_values = {
            "company_snapshot_id": str(company_snapshot_id),
            "company_snapshot_version": snapshot_version_value,
            "decision_case_id": str(decision_case_id),
            "generator_version": generator,
            "report_id": str(report_id),
            "report_version": report_version_value,
        }
        identity = hashlib.sha256(
            json.dumps(
                identity_values, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ).encode()
        ).hexdigest()
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            version=1,
            report_id=report_id,
            report_version=report_version_value,
            decision_case_id=decision_case_id,
            company_snapshot_id=company_snapshot_id,
            company_snapshot_version=snapshot_version_value,
            status=status,
            status_reason=reason,
            generator_version=generator,
            generation_identity=identity,
            created_at=_utc(now),
        )


def _positive(value: int) -> int:
    if isinstance(value, bool) or value < 1:
        raise DomainError("Version must be positive", error_code="invalid_version")
    return value


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return result.astimezone(timezone.utc)
