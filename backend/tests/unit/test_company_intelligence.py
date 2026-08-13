"""Company intelligence domain contract tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.application.decision import CompanyAssessmentUseCases
from app.domain.base.exceptions import DomainError
from app.domain.decision import CompanyAssessment, CompanyAssessmentStatus
from app.domain.knowledge import ArtifactStatus
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceReference,
    CompanySourceTier,
    Freshness,
)

NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


class _LookupRepository:
    def __init__(self, value: object | None) -> None:
        self.value = value

    async def get_by_id(self, _entity_id: object) -> object | None:
        return self.value


class _Source:
    def __init__(self, *, owner_id: object, source: CompanySourceReference) -> None:
        self.owner_id = owner_id
        self.version = source.source_version
        self.artifact_id = uuid4()
        self.artifact_version = 1


class _Artifact:
    def __init__(self, *, owner_id: object, artifact_id: object) -> None:
        self.id = artifact_id
        self.owner_id = owner_id
        self.version = 1
        self.status = ArtifactStatus.AVAILABLE


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


def _assessment_use_case(source: _Source, artifact: _Artifact) -> CompanyAssessmentUseCases:
    unused = _LookupRepository(None)
    return CompanyAssessmentUseCases(
        unused, unused, unused, unused, _LookupRepository(source), _LookupRepository(artifact)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tier", "age_days", "statuses", "expected_status", "expected_reason"),
    [
        (
            CompanySourceTier.OFFICIAL,
            30,
            (CompanyFieldStatus.CONFLICTED,) * 3,
            CompanyAssessmentStatus.CONFLICTED,
            "conflicted_fields",
        ),
        (
            CompanySourceTier.OFFICIAL,
            731,
            (CompanyFieldStatus.UNCONFIRMED,) * 3,
            CompanyAssessmentStatus.STALE,
            "source_stale",
        ),
        (
            CompanySourceTier.OFFICIAL,
            None,
            (CompanyFieldStatus.UNCONFIRMED,) * 3,
            CompanyAssessmentStatus.UNKNOWN,
            "source_freshness_unknown",
        ),
        (
            CompanySourceTier.ANONYMOUS_PLATFORM,
            30,
            (CompanyFieldStatus.UNCONFIRMED,) * 3,
            CompanyAssessmentStatus.UNKNOWN,
            "anonymous_source",
        ),
        (
            CompanySourceTier.OFFICIAL,
            30,
            (CompanyFieldStatus.SUPERSEDED,) * 3,
            CompanyAssessmentStatus.UNKNOWN,
            "superseded_fields",
        ),
        (
            CompanySourceTier.OFFICIAL,
            30,
            (CompanyFieldStatus.UNKNOWN,) * 3,
            CompanyAssessmentStatus.UNKNOWN,
            "incomplete_fields",
        ),
        (
            CompanySourceTier.VERIFIED_PLATFORM,
            30,
            (CompanyFieldStatus.UNCONFIRMED,) * 3,
            CompanyAssessmentStatus.AVAILABLE,
            "fixed_snapshot",
        ),
    ],
)
async def test_company_assessment_maps_source_and_field_states(
    tier: CompanySourceTier,
    age_days: int | None,
    statuses: tuple[CompanyFieldStatus, CompanyFieldStatus, CompanyFieldStatus],
    expected_status: CompanyAssessmentStatus,
    expected_reason: str,
) -> None:
    owner_id = uuid4()
    source_reference = _source(tier=tier, age_days=age_days)
    values = tuple(None if status is CompanyFieldStatus.UNKNOWN else "known" for status in statuses)
    snapshot = CompanySnapshot.create(
        owner_id=owner_id,
        company_name="Example Inc",
        size=values[0],
        size_status=statuses[0],
        industry=values[1],
        industry_status=statuses[1],
        review_summary=values[2],
        review_status=statuses[2],
        source=source_reference,
        now=NOW,
    )
    source = _Source(owner_id=owner_id, source=source_reference)
    artifact = _Artifact(owner_id=owner_id, artifact_id=source.artifact_id)

    status, reason = await _assessment_use_case(source, artifact)._status(owner_id, snapshot)

    assert (status, reason) == (expected_status, expected_reason)
