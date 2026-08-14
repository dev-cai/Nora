"""Deterministic PDF generation records for immutable resume variants."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError
from app.domain.followup.resume_variant import ResumeVariant, TemplateDefinition

PDF_CONTENT_TYPE = "application/pdf"
PDF_LOCALE = "zh-CN"
PDF_TIMEZONE = "UTC"


class ResumePdfStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ResumePdf:
    id: UUID
    owner_id: UUID
    version: int
    resume_variant_id: UUID
    resume_variant_version: int
    template_id: UUID
    template_version: int
    template_definition_hash: str
    variant_content_fingerprint: str
    renderer_version: str
    font_set_version: str
    locale: str
    timezone: str
    generation_identity: str
    status: ResumePdfStatus
    artifact_id: UUID | None
    artifact_version: int | None
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        variant: ResumeVariant,
        template: TemplateDefinition,
        renderer_version: str,
        font_set_version: str,
        locale: str = PDF_LOCALE,
        timezone_name: str = PDF_TIMEZONE,
        now: datetime | None = None,
    ) -> "ResumePdf":
        if (variant.template_id, variant.template_version) != (template.id, template.version):
            raise DomainError(
                "Resume PDF template does not match variant",
                error_code="invalid_resume_pdf_input",
            )
        renderer = _text(renderer_version, 100)
        fonts = _text(font_set_version, 100)
        normalized_locale = _text(locale, 20)
        normalized_timezone = _text(timezone_name, 50)
        identity = _digest(
            {
                "font_set_version": fonts,
                "locale": normalized_locale,
                "renderer_version": renderer,
                "resume_variant": [
                    str(variant.id),
                    variant.version,
                    variant.content_fingerprint,
                ],
                "template": [
                    str(template.id),
                    template.version,
                    template.definition_hash,
                ],
                "timezone": normalized_timezone,
            }
        )
        timestamp = _utc(now)
        return cls(
            id=uuid4(),
            owner_id=variant.owner_id,
            version=1,
            resume_variant_id=variant.id,
            resume_variant_version=variant.version,
            template_id=template.id,
            template_version=template.version,
            template_definition_hash=template.definition_hash,
            variant_content_fingerprint=variant.content_fingerprint,
            renderer_version=renderer,
            font_set_version=fonts,
            locale=normalized_locale,
            timezone=normalized_timezone,
            generation_identity=identity,
            status=ResumePdfStatus.PENDING,
            artifact_id=None,
            artifact_version=None,
            artifact_sha256=None,
            artifact_size_bytes=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @classmethod
    def restore(
        cls,
        *,
        pdf_id: UUID,
        owner_id: UUID,
        version: int,
        resume_variant_id: UUID,
        resume_variant_version: int,
        template_id: UUID,
        template_version: int,
        template_definition_hash: str,
        variant_content_fingerprint: str,
        renderer_version: str,
        font_set_version: str,
        locale: str,
        timezone_name: str,
        generation_identity: str,
        status: ResumePdfStatus,
        artifact_id: UUID | None,
        artifact_version: int | None,
        artifact_sha256: str | None,
        artifact_size_bytes: int | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> "ResumePdf":
        normalized_status = ResumePdfStatus(status)
        artifact_values = (
            artifact_id,
            artifact_version,
            artifact_sha256,
            artifact_size_bytes,
        )
        if normalized_status is ResumePdfStatus.AVAILABLE:
            if any(value is None for value in artifact_values):
                raise DomainError(
                    "Available Resume PDF requires an Artifact",
                    error_code="invalid_resume_pdf_state",
                )
        elif any(value is not None for value in artifact_values):
            raise DomainError(
                "Unavailable Resume PDF cannot expose an Artifact",
                error_code="invalid_resume_pdf_state",
            )
        return cls(
            id=pdf_id,
            owner_id=owner_id,
            version=_positive(version),
            resume_variant_id=resume_variant_id,
            resume_variant_version=_positive(resume_variant_version),
            template_id=template_id,
            template_version=_positive(template_version),
            template_definition_hash=_sha256(template_definition_hash),
            variant_content_fingerprint=_sha256(variant_content_fingerprint),
            renderer_version=_text(renderer_version, 100),
            font_set_version=_text(font_set_version, 100),
            locale=_text(locale, 20),
            timezone=_text(timezone_name, 50),
            generation_identity=_sha256(generation_identity),
            status=normalized_status,
            artifact_id=artifact_id,
            artifact_version=_positive(artifact_version) if artifact_version is not None else None,
            artifact_sha256=_sha256(artifact_sha256) if artifact_sha256 is not None else None,
            artifact_size_bytes=(
                _positive(artifact_size_bytes) if artifact_size_bytes is not None else None
            ),
            created_at=_utc(created_at),
            updated_at=_utc(updated_at),
        )

    def retry(self, now: datetime | None = None) -> "ResumePdf":
        if self.status not in {ResumePdfStatus.PENDING, ResumePdfStatus.FAILED}:
            raise DomainError(
                "Resume PDF cannot be retried", error_code="resume_pdf_state_conflict"
            )
        return replace(
            self,
            status=ResumePdfStatus.PENDING,
            artifact_id=None,
            artifact_version=None,
            artifact_sha256=None,
            artifact_size_bytes=None,
            updated_at=_utc(now),
        )

    def publish(
        self,
        *,
        artifact_id: UUID,
        artifact_version: int,
        artifact_sha256: str,
        artifact_size_bytes: int,
        now: datetime | None = None,
    ) -> "ResumePdf":
        if self.status is not ResumePdfStatus.PENDING:
            raise DomainError(
                "Resume PDF cannot be published", error_code="resume_pdf_state_conflict"
            )
        return replace(
            self,
            status=ResumePdfStatus.AVAILABLE,
            artifact_id=artifact_id,
            artifact_version=_positive(artifact_version),
            artifact_sha256=_sha256(artifact_sha256),
            artifact_size_bytes=_positive(artifact_size_bytes),
            updated_at=_utc(now),
        )

    def fail(self, now: datetime | None = None) -> "ResumePdf":
        if self.status not in {ResumePdfStatus.PENDING, ResumePdfStatus.FAILED}:
            raise DomainError("Resume PDF cannot fail", error_code="resume_pdf_state_conflict")
        return replace(
            self,
            status=ResumePdfStatus.FAILED,
            artifact_id=None,
            artifact_version=None,
            artifact_sha256=None,
            artifact_size_bytes=None,
            updated_at=_utc(now),
        )


def _text(value: str, maximum: int) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise DomainError("Resume PDF text is invalid", error_code="invalid_resume_pdf_input")
    return normalized


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Resume PDF version is invalid", error_code="invalid_resume_pdf_input")
    return value


def _sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise DomainError("Resume PDF hash is invalid", error_code="invalid_resume_pdf_input")
    return normalized


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return result.astimezone(timezone.utc)


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
