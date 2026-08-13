"""Company intelligence domain contract tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.domain.base.exceptions import DomainError
from app.domain.decision import CompanyAssessment, CompanyAssessmentStatus
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceReference,
    CompanySourceTier,
    Freshness,
)

NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _source(
    *,
    tier: CompanySourceTier = CompanySourceTier.OFFICIAL,
    age_days: int | None = 30,
) -> CompanySourceReference:
    return CompanySourceReference.create(
        source_id=uuid4(),
        source_version=1,
        source_tier=tier,
        source_kind="manual",
        acquisition_method="user_entry",
        license_note="user supplied",
        acquired_at=NOW,
        published_at=None if age_days is None else NOW - timedelta(days=age_days),
        content_sha256="a" * 64,
    )


def _snapshot(source: CompanySourceReference | None = None) -> CompanySnapshot:
    return CompanySnapshot.create(
        owner_id=uuid4(),
        company_name="Example Inc",
        size="100-499",
        size_status=CompanyFieldStatus.CONFIRMED,
        industry="Software",
        industry_status=CompanyFieldStatus.CONFIRMED,
        review_summary="Clear engineering ladder",
        review_status=CompanyFieldStatus.UNCONFIRMED,
        source=source or _source(),
        now=NOW,
    )


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(365, Freshness.FRESH), (366, Freshness.AGING), (730, Freshness.AGING)],
)
def test_company_snapshot_calculates_freshness_boundaries(
    age_days: int, expected: Freshness
) -> None:
    assert _snapshot(_source(age_days=age_days)).freshness is expected


def test_company_snapshot_rejects_missing_value_status_conflict() -> None:
    with pytest.raises(DomainError, match="value and status conflict"):
        CompanySnapshot.create(
            owner_id=uuid4(),
            company_name="Example Inc",
            size=None,
            size_status=CompanyFieldStatus.CONFIRMED,
            industry=None,
            industry_status=CompanyFieldStatus.UNKNOWN,
            review_summary=None,
            review_status=CompanyFieldStatus.UNKNOWN,
            source=_source(),
            now=NOW,
        )


def test_anonymous_and_stale_values_cannot_be_confirmed_facts() -> None:
    with pytest.raises(DomainError, match="Anonymous sources"):
        CompanySnapshot.create(
            owner_id=uuid4(),
            company_name="Example Inc",
            size="100-499",
            size_status=CompanyFieldStatus.CONFIRMED,
            industry=None,
            industry_status=CompanyFieldStatus.UNKNOWN,
            review_summary="Anonymous opinion",
            review_status=CompanyFieldStatus.UNCONFIRMED,
            source=_source(tier=CompanySourceTier.ANONYMOUS_PLATFORM),
            now=NOW,
        )
    with pytest.raises(DomainError, match="Stale company data"):
        _snapshot(_source(age_days=731))


def test_append_version_preserves_identity_and_prior_version() -> None:
    first = _snapshot()
    second = first.append_version(
        size="500-999",
        size_status=CompanyFieldStatus.UNCONFIRMED,
        industry=first.industry,
        industry_status=first.industry_status,
        review_summary=None,
        review_status=CompanyFieldStatus.UNKNOWN,
        source=_source(age_days=None),
        now=NOW + timedelta(days=1),
    )
    assert second.id == first.id
    assert second.version == 2
    assert first.version == 1
    assert first.size == "100-499"
    assert second.size == "500-999"
    assert first.content_sha256 != second.content_sha256


def test_company_assessment_generation_identity_is_deterministic_and_versioned() -> None:
    values = {
        "owner_id": uuid4(),
        "report_id": uuid4(),
        "report_version": 2,
        "decision_case_id": uuid4(),
        "decision_case_version": 1,
        "company_snapshot_id": uuid4(),
        "company_snapshot_version": 3,
        "status": CompanyAssessmentStatus.AVAILABLE,
        "status_reason": "fixed_snapshot",
        "generator_version": "m4-company-assessment-v1",
        "now": NOW,
    }
    first = CompanyAssessment.create(**values)
    replay = CompanyAssessment.create(**values)
    assert first.generation_identity == replay.generation_identity
    assert first.decision_case_version == 1
    assert first.company_snapshot_version == 3
    changed = CompanyAssessment.create(**{**values, "company_snapshot_version": 4})
    assert changed.generation_identity != first.generation_identity
