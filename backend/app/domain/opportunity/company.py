"""Immutable, versioned company intelligence snapshots."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode


class CompanyFieldStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"
    SUPERSEDED = "superseded"


class CompanySourceTier(StrEnum):
    OFFICIAL = "official/company"
    REPUTABLE_MEDIA = "reputable_media"
    VERIFIED_PLATFORM = "verified_platform"
    ANONYMOUS_PLATFORM = "anonymous_platform"


class Freshness(StrEnum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CompanySourceReference:
    """Fixed SourceDocument metadata safe to retain after source deletion."""

    source_id: UUID
    source_version: int
    source_tier: CompanySourceTier
    source_kind: str
    acquisition_method: str
    license_note: str
    acquired_at: datetime
    published_at: datetime | None
    content_sha256: str

    @classmethod
    def create(
        cls,
        *,
        source_id: UUID,
        source_version: int,
        source_tier: CompanySourceTier,
        source_kind: str,
        acquisition_method: str,
        license_note: str,
        acquired_at: datetime,
        published_at: datetime | None,
        content_sha256: str,
    ) -> "CompanySourceReference":
        kind = _text(source_kind, 32, required=True) or ""
        method = _text(acquisition_method, 100, required=True) or ""
        license_value = _text(license_note, 500, required=True) or ""
        digest = content_sha256.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise DomainError(
                "Source SHA-256 is invalid", error_code=ErrorCode.INVALID_SOURCE_SHA256
            )
        acquired = _utc(acquired_at)
        published = _utc(published_at) if published_at else None
        if published is not None and published > acquired:
            raise DomainError(
                "Published time is after acquisition", error_code=ErrorCode.INVALID_TIMESTAMP
            )
        return cls(
            source_id=source_id,
            source_version=_positive(source_version),
            source_tier=source_tier,
            source_kind=kind,
            acquisition_method=method,
            license_note=license_value,
            acquired_at=acquired,
            published_at=published,
            content_sha256=digest,
        )


@dataclass(frozen=True, slots=True)
class CompanySnapshot:
    id: UUID
    owner_id: UUID
    version: int
    company_name: str
    size: str | None
    size_status: CompanyFieldStatus
    industry: str | None
    industry_status: CompanyFieldStatus
    review_summary: str | None
    review_status: CompanyFieldStatus
    source: CompanySourceReference
    freshness: Freshness
    content_sha256: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        company_name: str,
        size: str | None,
        size_status: CompanyFieldStatus,
        industry: str | None,
        industry_status: CompanyFieldStatus,
        review_summary: str | None,
        review_status: CompanyFieldStatus,
        source: CompanySourceReference,
        now: datetime | None = None,
    ) -> "CompanySnapshot":
        return cls._build(
            snapshot_id=uuid4(),
            owner_id=owner_id,
            version=1,
            company_name=company_name,
            size=size,
            size_status=size_status,
            industry=industry,
            industry_status=industry_status,
            review_summary=review_summary,
            review_status=review_status,
            source=source,
            created_at=_utc(now),
        )

    def append_version(
        self,
        *,
        size: str | None,
        size_status: CompanyFieldStatus,
        industry: str | None,
        industry_status: CompanyFieldStatus,
        review_summary: str | None,
        review_status: CompanyFieldStatus,
        source: CompanySourceReference,
        now: datetime | None = None,
    ) -> "CompanySnapshot":
        return self._build(
            snapshot_id=self.id,
            owner_id=self.owner_id,
            version=self.version + 1,
            company_name=self.company_name,
            size=size,
            size_status=size_status,
            industry=industry,
            industry_status=industry_status,
            review_summary=review_summary,
            review_status=review_status,
            source=source,
            created_at=_utc(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        snapshot_id: UUID,
        owner_id: UUID,
        version: int,
        company_name: str,
        size: str | None,
        size_status: CompanyFieldStatus,
        industry: str | None,
        industry_status: CompanyFieldStatus,
        review_summary: str | None,
        review_status: CompanyFieldStatus,
        source: CompanySourceReference,
        freshness: Freshness,
        content_sha256: str,
        created_at: datetime,
    ) -> "CompanySnapshot":
        return cls(
            id=snapshot_id,
            owner_id=owner_id,
            version=_positive(version),
            company_name=company_name,
            size=size,
            size_status=size_status,
            industry=industry,
            industry_status=industry_status,
            review_summary=review_summary,
            review_status=review_status,
            source=source,
            freshness=freshness,
            content_sha256=content_sha256,
            created_at=_utc(created_at),
        )

    @classmethod
    def _build(
        cls,
        *,
        snapshot_id: UUID,
        owner_id: UUID,
        version: int,
        company_name: str,
        size: str | None,
        size_status: CompanyFieldStatus,
        industry: str | None,
        industry_status: CompanyFieldStatus,
        review_summary: str | None,
        review_status: CompanyFieldStatus,
        source: CompanySourceReference,
        created_at: datetime,
    ) -> "CompanySnapshot":
        name = _text(company_name, 200, required=True) or ""
        size_value = _text(size, 200)
        industry_value = _text(industry, 200)
        summary = _text(review_summary, 2_000)
        _validate_field(size_value, size_status)
        _validate_field(industry_value, industry_status)
        _validate_field(summary, review_status)
        freshness = _freshness(source.acquired_at, source.published_at)
        statuses = (size_status, industry_status, review_status)
        if freshness is Freshness.STALE and CompanyFieldStatus.CONFIRMED in statuses:
            raise DomainError(
                "Stale company data cannot be a confirmed current fact",
                error_code=ErrorCode.INVALID_COMPANY_FACT_STATUS,
            )
        if (
            source.source_tier is CompanySourceTier.ANONYMOUS_PLATFORM
            and CompanyFieldStatus.CONFIRMED in statuses
        ):
            raise DomainError(
                "Anonymous sources cannot provide confirmed facts",
                error_code=ErrorCode.INVALID_COMPANY_FACT_STATUS,
            )
        content = {
            "company_name": name,
            "industry": industry_value,
            "industry_status": industry_status.value,
            "review_status": review_status.value,
            "review_summary": summary,
            "size": size_value,
            "size_status": size_status.value,
            "source_content_sha256": source.content_sha256,
            "source_id": str(source.source_id),
            "source_version": source.source_version,
            "source_tier": source.source_tier.value,
        }
        digest = hashlib.sha256(
            json.dumps(content, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        return cls(
            id=snapshot_id,
            owner_id=owner_id,
            version=_positive(version),
            company_name=name,
            size=size_value,
            size_status=size_status,
            industry=industry_value,
            industry_status=industry_status,
            review_summary=summary,
            review_status=review_status,
            source=source,
            freshness=freshness,
            content_sha256=digest,
            created_at=created_at,
        )


def _validate_field(value: str | None, status: CompanyFieldStatus) -> None:
    if (value is None) != (status is CompanyFieldStatus.UNKNOWN):
        raise DomainError(
            "Company field value and status conflict",
            error_code=ErrorCode.INVALID_COMPANY_FACT_STATUS,
        )


def _freshness(acquired_at: datetime, published_at: datetime | None) -> Freshness:
    if published_at is None:
        return Freshness.UNKNOWN
    age = (acquired_at.date() - published_at.date()).days
    if age <= 365:
        return Freshness.FRESH
    if age <= 730:
        return Freshness.AGING
    return Freshness.STALE


def _text(value: str | None, maximum: int, *, required: bool = False) -> str | None:
    normalized = " ".join(value.split()) if value is not None else None
    if (required and not normalized) or (normalized is not None and len(normalized) > maximum):
        raise DomainError("Company text is invalid", error_code=ErrorCode.INVALID_COMPANY_TEXT)
    return normalized or None


def _positive(value: int) -> int:
    if isinstance(value, bool) or value < 1:
        raise DomainError("Version must be positive", error_code=ErrorCode.INVALID_VERSION)
    return value


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return result.astimezone(timezone.utc)
