"""Versioned, user-confirmed interview notification facts."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import TypedDict
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_INTERVIEW_LOCATION_LENGTH = 500
MAX_INTERVIEW_NOTE_LENGTH = 2_000
MAX_INTERVIEW_URL_LENGTH = 2_000
MAX_INTERVIEW_TIMEZONE_LENGTH = 100
MAX_INTERVIEW_ROUND = 20
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class InterviewMode(StrEnum):
    ONSITE = "onsite"
    ONLINE = "online"
    PHONE = "phone"


class InterviewCaseStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class InterviewCaseSource(StrEnum):
    USER_CONFIRMATION = "user_confirmation"


class _InterviewValues(TypedDict):
    starts_at: datetime
    timezone: str
    mode: InterviewMode
    location: str | None
    meeting_url: str | None
    round_number: int
    note: str | None
    status: InterviewCaseStatus


@dataclass(frozen=True, slots=True)
class InterviewCase:
    id: UUID
    owner_id: UUID
    application_record_id: UUID
    version: int
    actor_id: UUID
    starts_at: datetime
    timezone: str
    mode: InterviewMode
    location: str | None
    meeting_url: str | None
    round_number: int
    note: str | None
    source: InterviewCaseSource
    status: InterviewCaseStatus
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        actor_id: UUID,
        application_record_id: UUID,
        starts_at: datetime,
        timezone_name: str,
        mode: InterviewMode,
        location: str | None,
        meeting_url: str | None,
        round_number: int,
        note: str | None,
        status: InterviewCaseStatus,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "InterviewCase":
        timestamp = _utc(now)
        values = _normalized_values(
            starts_at=starts_at,
            timezone_name=timezone_name,
            mode=mode,
            location=location,
            meeting_url=meeting_url,
            round_number=round_number,
            note=note,
            status=status,
        )
        _validate_actor(owner_id, actor_id)
        fingerprint = interview_case_request_fingerprint(
            application_record_id=application_record_id,
            base_version=0,
            **values,
        )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            application_record_id=application_record_id,
            version=1,
            actor_id=actor_id,
            source=InterviewCaseSource.USER_CONFIRMATION,
            idempotency_key=normalize_interview_idempotency_key(idempotency_key),
            request_fingerprint=fingerprint,
            created_at=timestamp,
            updated_at=timestamp,
            **values,
        )

    def update(
        self,
        *,
        actor_id: UUID,
        starts_at: datetime,
        timezone_name: str,
        mode: InterviewMode,
        location: str | None,
        meeting_url: str | None,
        round_number: int,
        note: str | None,
        status: InterviewCaseStatus,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "InterviewCase":
        timestamp = _utc(now)
        _validate_actor(self.owner_id, actor_id)
        if self.starts_at <= timestamp:
            raise DomainError(
                "Past interview arrangements cannot be updated",
                error_code=ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT,
            )
        values = _normalized_values(
            starts_at=starts_at,
            timezone_name=timezone_name,
            mode=mode,
            location=location,
            meeting_url=meeting_url,
            round_number=round_number,
            note=note,
            status=status,
        )
        return replace(
            self,
            version=self.version + 1,
            actor_id=actor_id,
            source=InterviewCaseSource.USER_CONFIRMATION,
            idempotency_key=normalize_interview_idempotency_key(idempotency_key),
            request_fingerprint=interview_case_request_fingerprint(
                application_record_id=self.application_record_id,
                base_version=self.version,
                **values,
            ),
            updated_at=timestamp,
            **values,
        )

    @classmethod
    def restore(
        cls,
        *,
        case_id: UUID,
        owner_id: UUID,
        application_record_id: UUID,
        version: int,
        actor_id: UUID,
        starts_at: datetime,
        timezone_name: str,
        mode: InterviewMode,
        location: str | None,
        meeting_url: str | None,
        round_number: int,
        note: str | None,
        source: InterviewCaseSource,
        status: InterviewCaseStatus,
        idempotency_key: str,
        request_fingerprint: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> "InterviewCase":
        values = _normalized_values(
            starts_at=starts_at,
            timezone_name=timezone_name,
            mode=mode,
            location=location,
            meeting_url=meeting_url,
            round_number=round_number,
            note=note,
            status=status,
        )
        _validate_actor(owner_id, actor_id)
        restored_version = _positive_version(version)
        expected = interview_case_request_fingerprint(
            application_record_id=application_record_id,
            base_version=restored_version - 1,
            **values,
        )
        if request_fingerprint.strip().lower() != expected:
            raise DomainError(
                "Interview case fingerprint is invalid",
                error_code=ErrorCode.INVALID_INTERVIEW_CASE,
            )
        return cls(
            id=case_id,
            owner_id=owner_id,
            application_record_id=application_record_id,
            version=restored_version,
            actor_id=actor_id,
            source=InterviewCaseSource(source),
            idempotency_key=normalize_interview_idempotency_key(idempotency_key),
            request_fingerprint=expected,
            created_at=_utc(created_at),
            updated_at=_utc(updated_at),
            **values,
        )

    def has_same_request(self, fingerprint: str) -> bool:
        return self.request_fingerprint == fingerprint


def interview_case_request_fingerprint(
    *,
    application_record_id: UUID,
    base_version: int,
    starts_at: datetime,
    timezone: str,
    mode: InterviewMode,
    location: str | None,
    meeting_url: str | None,
    round_number: int,
    note: str | None,
    status: InterviewCaseStatus,
) -> str:
    values = {
        "application_record_id": str(application_record_id),
        "base_version": base_version,
        "starts_at": starts_at.isoformat(),
        "timezone": timezone,
        "mode": mode.value,
        "location": location,
        "meeting_url": meeting_url,
        "round_number": round_number,
        "note": note,
        "status": status.value,
    }
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def normalize_interview_idempotency_key(value: str) -> str:
    if not isinstance(value, str):
        raise DomainError(
            "Idempotency key must be text", error_code=ErrorCode.INVALID_IDEMPOTENCY_KEY
        )
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise DomainError(
            "Idempotency key must contain 1-255 characters",
            error_code=ErrorCode.INVALID_IDEMPOTENCY_KEY,
        )
    return normalized


def _normalized_values(
    *,
    starts_at: datetime,
    timezone_name: str,
    mode: InterviewMode,
    location: str | None,
    meeting_url: str | None,
    round_number: int,
    note: str | None,
    status: InterviewCaseStatus,
) -> _InterviewValues:
    try:
        normalized_mode = InterviewMode(mode)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Interview mode is invalid", error_code=ErrorCode.INVALID_INTERVIEW_MODE
        ) from exc
    try:
        normalized_status = InterviewCaseStatus(status)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Interview status is invalid", error_code=ErrorCode.INVALID_INTERVIEW_STATUS
        ) from exc
    normalized_timezone = _timezone_name(timezone_name)
    normalized_location = _optional_text(location, MAX_INTERVIEW_LOCATION_LENGTH)
    normalized_url = _meeting_url(meeting_url)
    if normalized_mode is InterviewMode.ONSITE:
        if normalized_location is None or normalized_url is not None:
            raise DomainError(
                "Onsite interviews require a location and no meeting URL",
                error_code=ErrorCode.INVALID_INTERVIEW_CASE,
            )
    elif normalized_mode is InterviewMode.ONLINE:
        if normalized_url is None or normalized_location is not None:
            raise DomainError(
                "Online interviews require a meeting URL and no location",
                error_code=ErrorCode.INVALID_INTERVIEW_CASE,
            )
    elif normalized_location is not None or normalized_url is not None:
        raise DomainError(
            "Phone interviews cannot include a location or meeting URL",
            error_code=ErrorCode.INVALID_INTERVIEW_CASE,
        )
    if (
        isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or not 1 <= round_number <= MAX_INTERVIEW_ROUND
    ):
        raise DomainError(
            "Interview round must be between 1 and 20",
            error_code=ErrorCode.INVALID_INTERVIEW_ROUND,
        )
    return _InterviewValues(
        starts_at=_utc(starts_at),
        timezone=normalized_timezone,
        mode=normalized_mode,
        location=normalized_location,
        meeting_url=normalized_url,
        round_number=round_number,
        note=_optional_text(note, MAX_INTERVIEW_NOTE_LENGTH),
        status=normalized_status,
    )


def _timezone_name(value: str) -> str:
    if not isinstance(value, str):
        raise DomainError(
            "Interview timezone is invalid", error_code=ErrorCode.INVALID_INTERVIEW_TIMEZONE
        )
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_INTERVIEW_TIMEZONE_LENGTH:
        raise DomainError(
            "Interview timezone is invalid", error_code=ErrorCode.INVALID_INTERVIEW_TIMEZONE
        )
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise DomainError(
            "Interview timezone is invalid", error_code=ErrorCode.INVALID_INTERVIEW_TIMEZONE
        ) from exc
    return normalized


def _meeting_url(value: str | None) -> str | None:
    normalized = _optional_text(value, MAX_INTERVIEW_URL_LENGTH)
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise DomainError("Meeting URL must be a safe HTTPS URL", error_code=ErrorCode.INVALID_URL)
    return normalized


def _optional_text(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(
            "Interview text must be text", error_code=ErrorCode.INVALID_INTERVIEW_CASE
        )
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise DomainError("Interview text is too long", error_code=ErrorCode.INVALID_INTERVIEW_CASE)
    return normalized


def _validate_actor(owner_id: UUID, actor_id: UUID) -> None:
    if actor_id != owner_id:
        raise DomainError(
            "Interview actor must be its owner", error_code=ErrorCode.INVALID_INTERVIEW_CASE
        )


def _positive_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Version must be positive", error_code=ErrorCode.INVALID_VERSION)
    return value


def _utc(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return timestamp.astimezone(timezone.utc)
