"""User-confirmed, auditable manual application records."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import TypedDict, cast
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_APPLICATION_NOTE_LENGTH = 1_000
MAX_APPLICATION_CHANNEL_LENGTH = 100
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class ApplicationRecordStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER_RECEIVED = "offer_received"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationTransitionSource(StrEnum):
    USER_CONFIRMATION = "user_confirmation"


_ALLOWED_TRANSITIONS: dict[ApplicationRecordStatus, frozenset[ApplicationRecordStatus]] = {
    ApplicationRecordStatus.PLANNED: frozenset(
        {ApplicationRecordStatus.APPLIED, ApplicationRecordStatus.WITHDRAWN}
    ),
    ApplicationRecordStatus.APPLIED: frozenset(
        {
            ApplicationRecordStatus.INTERVIEWING,
            ApplicationRecordStatus.REJECTED,
            ApplicationRecordStatus.WITHDRAWN,
        }
    ),
    ApplicationRecordStatus.INTERVIEWING: frozenset(
        {
            ApplicationRecordStatus.OFFER_RECEIVED,
            ApplicationRecordStatus.REJECTED,
            ApplicationRecordStatus.WITHDRAWN,
        }
    ),
    ApplicationRecordStatus.OFFER_RECEIVED: frozenset(),
    ApplicationRecordStatus.REJECTED: frozenset(),
    ApplicationRecordStatus.WITHDRAWN: frozenset(),
}


class _ApplicationMaterial(TypedDict):
    resume_variant_version: int
    variant_content_fingerprint: str
    resume_pdf_id: UUID | None
    resume_pdf_version: int | None
    artifact_id: UUID | None
    artifact_version: int | None
    artifact_sha256: str | None
    message_draft_id: UUID | None
    message_draft_version: int | None
    message_content_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    id: UUID
    owner_id: UUID
    created_by: UUID
    version: int
    status: ApplicationRecordStatus
    application_decision_id: UUID
    decision_case_id: UUID
    resume_variant_id: UUID
    resume_variant_version: int
    variant_content_fingerprint: str
    resume_pdf_id: UUID | None
    resume_pdf_version: int | None
    artifact_id: UUID | None
    artifact_version: int | None
    artifact_sha256: str | None
    message_draft_id: UUID | None
    message_draft_version: int | None
    message_content_fingerprint: str | None
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
        application_decision_id: UUID,
        decision_case_id: UUID,
        resume_variant_id: UUID,
        resume_variant_version: int,
        variant_content_fingerprint: str,
        idempotency_key: str,
        resume_pdf_id: UUID | None = None,
        resume_pdf_version: int | None = None,
        artifact_id: UUID | None = None,
        artifact_version: int | None = None,
        artifact_sha256: str | None = None,
        message_draft_id: UUID | None = None,
        message_draft_version: int | None = None,
        message_content_fingerprint: str | None = None,
        now: datetime | None = None,
    ) -> "ApplicationRecord":
        if actor_id != owner_id:
            raise DomainError(
                "Application record actor must be its owner",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        timestamp = _utc(now)
        material = _normalize_materials(
            resume_variant_version=resume_variant_version,
            variant_content_fingerprint=variant_content_fingerprint,
            resume_pdf_id=resume_pdf_id,
            resume_pdf_version=resume_pdf_version,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            artifact_sha256=artifact_sha256,
            message_draft_id=message_draft_id,
            message_draft_version=message_draft_version,
            message_content_fingerprint=message_content_fingerprint,
        )
        fingerprint = application_record_request_fingerprint(
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            resume_variant_id=resume_variant_id,
            **material,
        )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            created_by=actor_id,
            version=1,
            status=ApplicationRecordStatus.PLANNED,
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            resume_variant_id=resume_variant_id,
            idempotency_key=normalize_application_idempotency_key(idempotency_key),
            request_fingerprint=fingerprint,
            created_at=timestamp,
            updated_at=timestamp,
            **material,
        )

    @classmethod
    def restore(
        cls,
        *,
        record_id: UUID,
        owner_id: UUID,
        created_by: UUID,
        version: int,
        status: ApplicationRecordStatus,
        application_decision_id: UUID,
        decision_case_id: UUID,
        resume_variant_id: UUID,
        resume_variant_version: int,
        variant_content_fingerprint: str,
        resume_pdf_id: UUID | None,
        resume_pdf_version: int | None,
        artifact_id: UUID | None,
        artifact_version: int | None,
        artifact_sha256: str | None,
        message_draft_id: UUID | None,
        message_draft_version: int | None,
        message_content_fingerprint: str | None,
        idempotency_key: str,
        request_fingerprint: str,
        created_at: datetime,
        updated_at: datetime,
    ) -> "ApplicationRecord":
        if created_by != owner_id:
            raise DomainError(
                "Application record actor must be its owner",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        material = _normalize_materials(
            resume_variant_version=resume_variant_version,
            variant_content_fingerprint=variant_content_fingerprint,
            resume_pdf_id=resume_pdf_id,
            resume_pdf_version=resume_pdf_version,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            artifact_sha256=artifact_sha256,
            message_draft_id=message_draft_id,
            message_draft_version=message_draft_version,
            message_content_fingerprint=message_content_fingerprint,
        )
        expected = application_record_request_fingerprint(
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            resume_variant_id=resume_variant_id,
            **material,
        )
        if _sha256(request_fingerprint) != expected:
            raise DomainError(
                "Application record fingerprint is invalid",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        try:
            restored_status = ApplicationRecordStatus(status)
        except (TypeError, ValueError) as exc:
            raise DomainError(
                "Application record status is invalid",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD_STATUS,
            ) from exc
        return cls(
            id=record_id,
            owner_id=owner_id,
            created_by=created_by,
            version=_positive(version),
            status=restored_status,
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            resume_variant_id=resume_variant_id,
            idempotency_key=normalize_application_idempotency_key(idempotency_key),
            request_fingerprint=expected,
            created_at=_utc(created_at),
            updated_at=_utc(updated_at),
            **material,
        )

    def transition(
        self,
        *,
        actor_id: UUID,
        to_status: ApplicationRecordStatus,
        occurred_at: datetime,
        channel: str | None,
        note: str | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> tuple["ApplicationRecord", "ApplicationRecordTransition"]:
        if actor_id != self.owner_id:
            raise DomainError(
                "Application transition actor must be its owner",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        try:
            target = ApplicationRecordStatus(to_status)
        except (TypeError, ValueError) as exc:
            raise DomainError(
                "Application record status is invalid",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD_STATUS,
            ) from exc
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise DomainError(
                f"Application record cannot transition from {self.status} to {target}",
                error_code=ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT,
            )
        normalized_channel = _optional_text(channel, MAX_APPLICATION_CHANNEL_LENGTH)
        if target is ApplicationRecordStatus.APPLIED and normalized_channel is None:
            raise DomainError(
                "Applied confirmation requires a channel",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        transition = ApplicationRecordTransition.create(
            owner_id=self.owner_id,
            application_record_id=self.id,
            record_version=self.version + 1,
            actor_id=actor_id,
            from_status=self.status,
            to_status=target,
            source=ApplicationTransitionSource.USER_CONFIRMATION,
            channel=normalized_channel,
            note=note,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            now=now,
        )
        return (
            replace(
                self,
                version=self.version + 1,
                status=target,
                updated_at=transition.recorded_at,
            ),
            transition,
        )

    def has_same_request(self, other: "ApplicationRecord") -> bool:
        return self.request_fingerprint == other.request_fingerprint


@dataclass(frozen=True, slots=True)
class ApplicationRecordTransition:
    id: UUID
    owner_id: UUID
    application_record_id: UUID
    record_version: int
    actor_id: UUID
    from_status: ApplicationRecordStatus
    to_status: ApplicationRecordStatus
    source: ApplicationTransitionSource
    channel: str | None
    note: str | None
    occurred_at: datetime
    recorded_at: datetime
    idempotency_key: str
    request_fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        application_record_id: UUID,
        record_version: int,
        actor_id: UUID,
        from_status: ApplicationRecordStatus,
        to_status: ApplicationRecordStatus,
        source: ApplicationTransitionSource,
        channel: str | None,
        note: str | None,
        occurred_at: datetime,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "ApplicationRecordTransition":
        if actor_id != owner_id:
            raise DomainError(
                "Application transition actor must be its owner",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        normalized_channel = _optional_text(channel, MAX_APPLICATION_CHANNEL_LENGTH)
        normalized_note = _optional_text(note, MAX_APPLICATION_NOTE_LENGTH)
        normalized_key = normalize_application_idempotency_key(idempotency_key)
        happened = _utc(occurred_at)
        record_version = _positive(record_version)
        if record_version < 2:
            raise DomainError(
                "Transition version must be at least two",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        fingerprint = application_transition_request_fingerprint(
            application_record_id=application_record_id,
            base_version=record_version - 1,
            to_status=to_status,
            occurred_at=happened,
            channel=normalized_channel,
            note=normalized_note,
        )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            application_record_id=application_record_id,
            record_version=record_version,
            actor_id=actor_id,
            from_status=ApplicationRecordStatus(from_status),
            to_status=ApplicationRecordStatus(to_status),
            source=ApplicationTransitionSource(source),
            channel=normalized_channel,
            note=normalized_note,
            occurred_at=happened,
            recorded_at=_utc(now),
            idempotency_key=normalized_key,
            request_fingerprint=fingerprint,
        )

    @classmethod
    def restore(
        cls,
        *,
        transition_id: UUID,
        owner_id: UUID,
        application_record_id: UUID,
        record_version: int,
        actor_id: UUID,
        from_status: ApplicationRecordStatus,
        to_status: ApplicationRecordStatus,
        source: ApplicationTransitionSource,
        channel: str | None,
        note: str | None,
        occurred_at: datetime,
        recorded_at: datetime,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> "ApplicationRecordTransition":
        restored = cls.create(
            owner_id=owner_id,
            application_record_id=application_record_id,
            record_version=record_version,
            actor_id=actor_id,
            from_status=from_status,
            to_status=to_status,
            source=source,
            channel=channel,
            note=note,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            now=recorded_at,
        )
        if restored.request_fingerprint != _sha256(request_fingerprint):
            raise DomainError(
                "Application transition fingerprint is invalid",
                error_code=ErrorCode.INVALID_APPLICATION_RECORD,
            )
        return replace(restored, id=transition_id)

    def has_same_request(self, other: "ApplicationRecordTransition") -> bool:
        return self.request_fingerprint == other.request_fingerprint


def normalize_application_idempotency_key(value: str) -> str:
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


def application_record_request_fingerprint(**values: object) -> str:
    return _digest(values)


def application_transition_request_fingerprint(
    *,
    application_record_id: UUID,
    base_version: int,
    to_status: ApplicationRecordStatus,
    occurred_at: datetime,
    channel: str | None,
    note: str | None,
) -> str:
    normalized_channel = _optional_text(channel, MAX_APPLICATION_CHANNEL_LENGTH)
    normalized_note = _optional_text(note, MAX_APPLICATION_NOTE_LENGTH)
    return _digest(
        {
            "application_record_id": str(application_record_id),
            "base_version": _positive(base_version),
            "channel": normalized_channel,
            "note": normalized_note,
            "occurred_at": _utc(occurred_at).isoformat(),
            "to_status": ApplicationRecordStatus(to_status).value,
        }
    )


def _normalize_materials(**values: object) -> _ApplicationMaterial:
    result: dict[str, object] = {
        "resume_variant_version": _positive(values["resume_variant_version"]),
        "variant_content_fingerprint": _sha256(values["variant_content_fingerprint"]),
        "resume_pdf_id": values["resume_pdf_id"],
        "resume_pdf_version": values["resume_pdf_version"],
        "artifact_id": values["artifact_id"],
        "artifact_version": values["artifact_version"],
        "artifact_sha256": values["artifact_sha256"],
        "message_draft_id": values["message_draft_id"],
        "message_draft_version": values["message_draft_version"],
        "message_content_fingerprint": values["message_content_fingerprint"],
    }
    pdf_keys = (
        "resume_pdf_id",
        "resume_pdf_version",
        "artifact_id",
        "artifact_version",
        "artifact_sha256",
    )
    draft_keys = ("message_draft_id", "message_draft_version", "message_content_fingerprint")
    if any(result[key] is not None for key in pdf_keys) != all(
        result[key] is not None for key in pdf_keys
    ):
        raise DomainError(
            "Resume PDF reference is incomplete", error_code=ErrorCode.INVALID_APPLICATION_RECORD
        )
    if any(result[key] is not None for key in draft_keys) != all(
        result[key] is not None for key in draft_keys
    ):
        raise DomainError(
            "Message draft reference is incomplete",
            error_code=ErrorCode.INVALID_APPLICATION_RECORD,
        )
    if result["resume_pdf_version"] is not None:
        result["resume_pdf_version"] = _positive(result["resume_pdf_version"])
        result["artifact_version"] = _positive(result["artifact_version"])
        result["artifact_sha256"] = _sha256(result["artifact_sha256"])
    if result["message_draft_version"] is not None:
        result["message_draft_version"] = _positive(result["message_draft_version"])
        result["message_content_fingerprint"] = _sha256(result["message_content_fingerprint"])
    return _ApplicationMaterial(
        resume_variant_version=cast(int, result["resume_variant_version"]),
        variant_content_fingerprint=cast(str, result["variant_content_fingerprint"]),
        resume_pdf_id=cast(UUID | None, result["resume_pdf_id"]),
        resume_pdf_version=cast(int | None, result["resume_pdf_version"]),
        artifact_id=cast(UUID | None, result["artifact_id"]),
        artifact_version=cast(int | None, result["artifact_version"]),
        artifact_sha256=cast(str | None, result["artifact_sha256"]),
        message_draft_id=cast(UUID | None, result["message_draft_id"]),
        message_draft_version=cast(int | None, result["message_draft_version"]),
        message_content_fingerprint=cast(str | None, result["message_content_fingerprint"]),
    )


def _positive(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Version must be positive", error_code=ErrorCode.INVALID_VERSION)
    return value


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(
            "Application record text must be text",
            error_code=ErrorCode.INVALID_APPLICATION_RECORD,
        )
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise DomainError(
            "Application record text is too long",
            error_code=ErrorCode.INVALID_APPLICATION_RECORD,
        )
    return normalized


def _utc(value: object) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if (
        not isinstance(timestamp, datetime)
        or timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return timestamp.astimezone(timezone.utc)


def _sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise DomainError(
            "Fingerprint must be SHA-256", error_code=ErrorCode.INVALID_APPLICATION_RECORD
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise DomainError(
            "Fingerprint must be SHA-256", error_code=ErrorCode.INVALID_APPLICATION_RECORD
        ) from exc
    return value.lower()


def _digest(values: object) -> str:
    canonical = json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
