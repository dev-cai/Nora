"""Declarative resume templates and immutable tailored resume variants."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_VARIANT_TITLE_LENGTH = 200
MAX_BLOCK_TEXT_LENGTH = 4_000
VARIANT_GENERATOR_VERSION = "m4-resume-variant-v1"


class TemplatePageSize(StrEnum):
    A4 = "a4"
    LETTER = "letter"


class TemplateDensity(StrEnum):
    COMPACT = "compact"
    STANDARD = "standard"


class TemplateAccent(StrEnum):
    NEUTRAL = "neutral"
    BLUE = "blue"


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    id: UUID
    version: int
    name: str
    page_size: TemplatePageSize
    density: TemplateDensity
    accent: TemplateAccent
    section_order: tuple[str, ...]
    allowed_fields: tuple[str, ...]
    required_fields: tuple[str, ...]
    definition_hash: str
    published_at: datetime

    @classmethod
    def create(
        cls,
        *,
        template_id: UUID,
        version: int,
        name: str,
        page_size: TemplatePageSize,
        density: TemplateDensity,
        accent: TemplateAccent,
        section_order: tuple[str, ...],
        allowed_fields: tuple[str, ...],
        required_fields: tuple[str, ...],
        published_at: datetime,
    ) -> "TemplateDefinition":
        normalized_name = _text(name, 100)
        sections = _unique_values(
            section_order, _ALLOWED_SECTIONS, ErrorCode.INVALID_TEMPLATE_SECTION
        )
        allowed = _unique_paths(allowed_fields)
        required = _unique_paths(required_fields)
        if any(not any(_matches(pattern, field) for pattern in allowed) for field in required):
            raise DomainError(
                "Required template fields must be allowed",
                error_code=ErrorCode.INVALID_TEMPLATE_FIELD,
            )
        normalized_version = _positive(version)
        content = {
            "accent": TemplateAccent(accent).value,
            "allowed_fields": allowed,
            "density": TemplateDensity(density).value,
            "name": normalized_name,
            "page_size": TemplatePageSize(page_size).value,
            "required_fields": required,
            "section_order": sections,
            "version": normalized_version,
        }
        return cls(
            id=template_id,
            version=normalized_version,
            name=normalized_name,
            page_size=TemplatePageSize(page_size),
            density=TemplateDensity(density),
            accent=TemplateAccent(accent),
            section_order=sections,
            allowed_fields=allowed,
            required_fields=required,
            definition_hash=_digest(content),
            published_at=_utc(published_at),
        )


@dataclass(frozen=True, slots=True)
class VariantBlock:
    source_path: str
    label: str
    value: str

    @classmethod
    def create(cls, *, source_path: str, label: str, value: str) -> "VariantBlock":
        path = _field_path(source_path, allow_wildcard=False)
        return cls(
            source_path=path,
            label=_text(label, 100),
            value=_text(value, MAX_BLOCK_TEXT_LENGTH),
        )


@dataclass(frozen=True, slots=True)
class ResumeVariant:
    id: UUID
    owner_id: UUID
    version: int
    application_decision_id: UUID
    decision_case_id: UUID
    job_posting_id: UUID
    job_posting_version: int
    job_requirement_snapshot_id: UUID
    job_requirement_snapshot_version: int
    resume_version_id: UUID
    resume_version: int
    template_id: UUID
    template_version: int
    title: str
    blocks: tuple[VariantBlock, ...]
    generator_version: str
    content_fingerprint: str
    idempotency_key: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        application_decision_id: UUID,
        decision_case_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        job_requirement_snapshot_id: UUID,
        job_requirement_snapshot_version: int,
        resume_version_id: UUID,
        resume_version: int,
        template: TemplateDefinition,
        resume_content: dict[str, Any],
        title: str,
        blocks: tuple[VariantBlock, ...],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "ResumeVariant":
        return cls._build(
            variant_id=uuid4(),
            owner_id=owner_id,
            version=1,
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            job_posting_id=job_posting_id,
            job_posting_version=job_posting_version,
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            job_requirement_snapshot_version=job_requirement_snapshot_version,
            resume_version_id=resume_version_id,
            resume_version=resume_version,
            template=template,
            resume_content=resume_content,
            title=title,
            blocks=blocks,
            idempotency_key=idempotency_key,
            created_at=_utc(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        variant_id: UUID,
        owner_id: UUID,
        version: int,
        application_decision_id: UUID,
        decision_case_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        job_requirement_snapshot_id: UUID,
        job_requirement_snapshot_version: int,
        resume_version_id: UUID,
        resume_version: int,
        template_id: UUID,
        template_version: int,
        title: str,
        blocks: tuple[VariantBlock, ...],
        generator_version: str,
        content_fingerprint: str,
        idempotency_key: str,
        created_at: datetime,
    ) -> "ResumeVariant":
        return cls(
            id=variant_id,
            owner_id=owner_id,
            version=_positive(version),
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            job_posting_id=job_posting_id,
            job_posting_version=_positive(job_posting_version),
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            job_requirement_snapshot_version=_positive(job_requirement_snapshot_version),
            resume_version_id=resume_version_id,
            resume_version=_positive(resume_version),
            template_id=template_id,
            template_version=_positive(template_version),
            title=_text(title, MAX_VARIANT_TITLE_LENGTH),
            blocks=tuple(
                VariantBlock.create(
                    source_path=item.source_path, label=item.label, value=item.value
                )
                for item in blocks
            ),
            generator_version=_text(generator_version, 100),
            content_fingerprint=_sha256(content_fingerprint),
            idempotency_key=_text(idempotency_key, 255),
            created_at=_utc(created_at),
        )

    @classmethod
    def _build(
        cls,
        *,
        variant_id: UUID,
        owner_id: UUID,
        version: int,
        application_decision_id: UUID,
        decision_case_id: UUID,
        job_posting_id: UUID,
        job_posting_version: int,
        job_requirement_snapshot_id: UUID,
        job_requirement_snapshot_version: int,
        resume_version_id: UUID,
        resume_version: int,
        template: TemplateDefinition,
        resume_content: dict[str, Any],
        title: str,
        blocks: tuple[VariantBlock, ...],
        idempotency_key: str,
        created_at: datetime,
    ) -> "ResumeVariant":
        normalized_blocks = tuple(
            VariantBlock.create(source_path=item.source_path, label=item.label, value=item.value)
            for item in blocks
        )
        if not normalized_blocks or len(normalized_blocks) > 100:
            raise DomainError(
                "Resume variant blocks are invalid", error_code=ErrorCode.INVALID_VARIANT_BLOCKS
            )
        paths = tuple(item.source_path for item in normalized_blocks)
        if len(paths) != len(set(paths)):
            raise DomainError(
                "Resume variant fields must be unique", error_code=ErrorCode.INVALID_VARIANT_BLOCKS
            )
        source_paths = _resume_leaf_paths(resume_content)
        if any(path not in source_paths for path in paths):
            raise DomainError(
                "Resume variant field is unavailable", error_code=ErrorCode.INVALID_VARIANT_FIELD
            )
        if any(not _template_allows(template, path) for path in paths):
            raise DomainError(
                "Resume variant field is not allowed", error_code=ErrorCode.INVALID_VARIANT_FIELD
            )
        if any(
            not any(_matches(required, path) for path in paths)
            for required in template.required_fields
        ):
            raise DomainError(
                "Resume variant misses a required field",
                error_code=ErrorCode.REQUIRED_VARIANT_FIELD,
            )
        normalized_job_version = _positive(job_posting_version)
        normalized_requirement_version = _positive(job_requirement_snapshot_version)
        normalized_resume_version = _positive(resume_version)
        normalized_title = _text(title, MAX_VARIANT_TITLE_LENGTH)
        fixed = {
            "application_decision_id": str(application_decision_id),
            "blocks": [
                {"label": item.label, "source_path": item.source_path, "value": item.value}
                for item in normalized_blocks
            ],
            "decision_case_id": str(decision_case_id),
            "generator_version": VARIANT_GENERATOR_VERSION,
            "job_posting": [str(job_posting_id), normalized_job_version],
            "job_requirement_snapshot": [
                str(job_requirement_snapshot_id),
                normalized_requirement_version,
            ],
            "resume_version": [str(resume_version_id), normalized_resume_version],
            "template": [str(template.id), template.version, template.definition_hash],
            "title": normalized_title,
        }
        return cls(
            id=variant_id,
            owner_id=owner_id,
            version=_positive(version),
            application_decision_id=application_decision_id,
            decision_case_id=decision_case_id,
            job_posting_id=job_posting_id,
            job_posting_version=normalized_job_version,
            job_requirement_snapshot_id=job_requirement_snapshot_id,
            job_requirement_snapshot_version=normalized_requirement_version,
            resume_version_id=resume_version_id,
            resume_version=normalized_resume_version,
            template_id=template.id,
            template_version=template.version,
            title=normalized_title,
            blocks=normalized_blocks,
            generator_version=VARIANT_GENERATOR_VERSION,
            content_fingerprint=_digest(fixed),
            idempotency_key=_text(idempotency_key, 255),
            created_at=created_at,
        )


_ALLOWED_SECTIONS = frozenset({"basic_information", "experiences", "education", "skills"})


def _resume_leaf_paths(content: dict[str, Any]) -> set[str]:
    paths: set[str] = set()

    def visit(value: Any, prefix: str) -> None:
        if isinstance(value, dict):
            item_id = value.get("id")
            for key, child in value.items():
                if key == "id":
                    continue
                segment = str(item_id) if item_id and prefix in _ALLOWED_SECTIONS else key
                child_prefix = f"{prefix}.{segment}.{key}" if segment != key else f"{prefix}.{key}"
                visit(child, child_prefix)
        elif isinstance(value, list):
            for item in value:
                visit(item, prefix)
        elif isinstance(value, (str, int, float, bool)) and not isinstance(value, type(None)):
            paths.add(prefix)

    for section, value in content.items():
        if section in _ALLOWED_SECTIONS:
            visit(value, section)
    return paths


def _template_allows(template: TemplateDefinition, path: str) -> bool:
    return any(_matches(pattern, path) for pattern in template.allowed_fields)


def _matches(pattern: str, path: str) -> bool:
    expected = pattern.split(".")
    actual = path.split(".")
    return len(expected) == len(actual) and all(
        a == b or a == "*" for a, b in zip(expected, actual)
    )


def _field_path(value: str, *, allow_wildcard: bool) -> str:
    path = value.strip()
    parts = path.split(".")
    if (
        len(parts) < 2
        or parts[0] not in _ALLOWED_SECTIONS
        or any(not part or part in {"__proto__", "constructor", "prototype"} for part in parts)
        or any(
            part != "*" or not allow_wildcard
            if part == "*"
            else not all(char.isalnum() or char in {"_", "-"} for char in part)
            for part in parts
        )
    ):
        raise DomainError(
            "Template field path is invalid", error_code=ErrorCode.INVALID_TEMPLATE_FIELD
        )
    return path


def _unique_paths(values: tuple[str, ...]) -> tuple[str, ...]:
    paths = tuple(_field_path(value, allow_wildcard=True) for value in values)
    if not paths or len(paths) != len(set(paths)):
        raise DomainError(
            "Template fields are invalid", error_code=ErrorCode.INVALID_TEMPLATE_FIELD
        )
    return paths


def _unique_values(
    values: tuple[str, ...], allowed: frozenset[str], error_code: ErrorCode
) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized or len(normalized) != len(set(normalized)) or not set(normalized) <= allowed:
        raise DomainError("Template values are invalid", error_code=error_code)
    return normalized


def _text(value: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise DomainError("Text value is invalid", error_code=ErrorCode.INVALID_VARIANT_TEXT)
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise DomainError("Text value is invalid", error_code=ErrorCode.INVALID_VARIANT_TEXT)
    return normalized


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Version must be positive", error_code=ErrorCode.INVALID_VERSION)
    return value


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return result.astimezone(timezone.utc)


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise DomainError(
            "Fingerprint is invalid", error_code=ErrorCode.INVALID_VARIANT_FINGERPRINT
        )
    return normalized
