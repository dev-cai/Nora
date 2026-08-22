"""用户材料导入的候选 Session/Draft 领域边界。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_IMPORT_TEXT_LENGTH = 100_000
MAX_IMPORT_FINGERPRINT_LENGTH = 64


class ImportType(StrEnum):
    JD = "jd"


class ImportSourceType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    URL = "url"


class ImportSessionStatus(StrEnum):
    CREATED = "created"
    DRAFT_READY = "draft_ready"
    FAILED = "failed"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class ImportSession:
    id: UUID
    owner_id: UUID
    import_type: ImportType
    source_type: ImportSourceType
    source_url: str | None
    status: ImportSessionStatus
    current_draft_id: UUID | None
    confirmed_job_posting_id: UUID | None
    confirmed_requirement_snapshot_id: UUID | None
    failure_code: ErrorCode | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        source_type: ImportSourceType,
        source_url: str | None = None,
        now: datetime | None = None,
    ) -> "ImportSession":
        if not isinstance(source_type, ImportSourceType):
            raise DomainError(
                "Import source type is invalid", error_code=ErrorCode.INVALID_INPUT_KIND
            )
        if source_type is ImportSourceType.URL and not source_url:
            raise DomainError(
                "URL import requires source_url", error_code=ErrorCode.INVALID_SOURCE_URL
            )
        timestamp = _utc_timestamp(now)
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            import_type=ImportType.JD,
            source_type=source_type,
            source_url=source_url.strip() if source_url else None,
            status=ImportSessionStatus.CREATED,
            current_draft_id=None,
            confirmed_job_posting_id=None,
            confirmed_requirement_snapshot_id=None,
            failure_code=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def with_draft(self, draft_id: UUID, *, now: datetime | None = None) -> "ImportSession":
        return self._replace(
            status=ImportSessionStatus.DRAFT_READY,
            current_draft_id=draft_id,
            failure_code=None,
            now=now,
        )

    def failed(self, error_code: ErrorCode, *, now: datetime | None = None) -> "ImportSession":
        return self._replace(
            status=ImportSessionStatus.FAILED,
            failure_code=error_code,
            now=now,
        )

    def confirmed(
        self,
        *,
        job_posting_id: UUID,
        requirement_snapshot_id: UUID,
        now: datetime | None = None,
    ) -> "ImportSession":
        return self._replace(
            status=ImportSessionStatus.CONFIRMED,
            confirmed_job_posting_id=job_posting_id,
            confirmed_requirement_snapshot_id=requirement_snapshot_id,
            now=now,
        )

    def _replace(self, *, now: datetime | None = None, **changes: Any) -> "ImportSession":
        changes["updated_at"] = _utc_timestamp(now)
        return ImportSession(
            self.id,
            self.owner_id,
            self.import_type,
            self.source_type,
            self.source_url,
            changes.get("status", self.status),
            changes.get("current_draft_id", self.current_draft_id),
            changes.get("confirmed_job_posting_id", self.confirmed_job_posting_id),
            changes.get(
                "confirmed_requirement_snapshot_id", self.confirmed_requirement_snapshot_id
            ),
            changes.get("failure_code", self.failure_code),
            self.created_at,
            changes["updated_at"],
        )


@dataclass(frozen=True, slots=True)
class ImportDraft:
    id: UUID
    session_id: UUID
    owner_id: UUID
    import_type: ImportType
    version: int
    content: dict[str, Any]
    content_fingerprint: str
    prompt_version: str
    model_version: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        session_id: UUID,
        owner_id: UUID,
        content: dict[str, Any],
        prompt_version: str,
        model_version: str,
        now: datetime | None = None,
    ) -> "ImportDraft":
        normalized = _normalize_content(content)
        timestamp = _utc_timestamp(now)
        return cls(
            id=uuid4(),
            session_id=session_id,
            owner_id=owner_id,
            import_type=ImportType.JD,
            version=1,
            content=normalized,
            content_fingerprint=content_fingerprint(normalized),
            prompt_version=_version(prompt_version),
            model_version=_version(model_version),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def edit(
        self,
        *,
        base_version: int,
        content: dict[str, Any],
        now: datetime | None = None,
    ) -> "ImportDraft":
        if base_version != self.version:
            raise DomainError(
                "Import draft version conflict", error_code=ErrorCode.IMPORT_DRAFT_VERSION_CONFLICT
            )
        normalized = _normalize_content(content)
        return ImportDraft(
            self.id,
            self.session_id,
            self.owner_id,
            self.import_type,
            self.version + 1,
            normalized,
            content_fingerprint(normalized),
            self.prompt_version,
            self.model_version,
            self.created_at,
            _utc_timestamp(now),
        )


def content_fingerprint(content: dict[str, Any]) -> str:
    return sha256(_canonical_json(_normalize_content(content)).encode("utf-8")).hexdigest()


def _normalize_content(content: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise DomainError(
            "Import draft content must be an object", error_code=ErrorCode.INVALID_DRAFT_TEXT
        )
    jd_text = content.get("jd_text")
    if not isinstance(jd_text, str) or not jd_text.strip():
        raise DomainError("Import draft JD text is empty", error_code=ErrorCode.INVALID_DRAFT_TEXT)
    if len(jd_text.strip()) > MAX_IMPORT_TEXT_LENGTH:
        raise DomainError("Import draft JD text is too long", error_code=ErrorCode.JD_TEXT_TOO_LONG)
    requirements = content.get("requirements")
    if not isinstance(requirements, dict):
        raise DomainError(
            "Import draft requirements are invalid", error_code=ErrorCode.INVALID_REQUIREMENT
        )
    return {
        "jd_text": jd_text.replace("\r\n", "\n").replace("\r", "\n").strip(),
        "job_title": _optional_text(content.get("job_title")),
        "company_name": _optional_text(content.get("company_name")),
        "location": _optional_text(content.get("location")),
        "requirements": requirements,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(
            "Import draft metadata is invalid", error_code=ErrorCode.INVALID_DRAFT_TEXT
        )
    normalized = " ".join(value.split())
    return normalized or None


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _version(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 100:
        raise DomainError("Import version is invalid", error_code=ErrorCode.INVALID_VERSION)
    return normalized


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return timestamp.astimezone(timezone.utc)


__all__ = (
    "ImportDraft",
    "ImportSession",
    "ImportSessionStatus",
    "ImportSourceType",
    "ImportType",
    "content_fingerprint",
)
