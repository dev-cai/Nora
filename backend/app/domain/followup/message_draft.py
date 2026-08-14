"""Deterministic, append-only message drafts for manual user delivery."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError

MESSAGE_DRAFT_GENERATOR_VERSION = "m4-message-draft-v1"
MESSAGE_DRAFT_TEMPLATE_VERSION = "message-template-v1"
MAX_DRAFT_TEXT_LENGTH = 4_000
MAX_USER_NOTE_LENGTH = 1_000
MAX_REFERRAL_CONTEXT_LENGTH = 1_000


class MessageDraftStyle(StrEnum):
    PROFESSIONAL = "professional"
    CONCISE = "concise"
    REFERRAL = "referral"


class MessageDraftRevisionType(StrEnum):
    GENERATED = "generated"
    EDITED = "edited"


@dataclass(frozen=True, slots=True)
class MessageDraftSource:
    application_decision_id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    resume_variant_id: UUID
    resume_variant_version: int
    variant_content_fingerprint: str
    candidate_profile_id: UUID
    candidate_profile_version: int
    resume_version_id: UUID
    resume_version: int
    job_posting_id: UUID
    job_posting_version: int
    display_name: str
    company_name: str
    job_title: str
    skills: tuple[str, ...]
    company_snapshot_id: UUID | None = None
    company_snapshot_version: int | None = None
    company_snapshot_hash: str | None = None
    company_freshness: str | None = None
    company_industry: str | None = None

    def normalized(self) -> "MessageDraftSource":
        company_values = (
            self.company_snapshot_id,
            self.company_snapshot_version,
            self.company_snapshot_hash,
            self.company_freshness,
        )
        if any(value is not None for value in company_values) and not all(
            value is not None for value in company_values
        ):
            raise DomainError(
                "Company snapshot identity is incomplete",
                error_code="invalid_message_draft_source",
            )
        return replace(
            self,
            report_version=_positive(self.report_version),
            resume_variant_version=_positive(self.resume_variant_version),
            variant_content_fingerprint=_sha256(self.variant_content_fingerprint),
            candidate_profile_version=_positive(self.candidate_profile_version),
            resume_version=_positive(self.resume_version),
            job_posting_version=_positive(self.job_posting_version),
            display_name=_text(self.display_name, 200, required=True) or "",
            company_name=_text(self.company_name, 200, required=True) or "",
            job_title=_text(self.job_title, 200, required=True) or "",
            skills=_unique_texts(self.skills, 20, 200),
            company_snapshot_version=(
                None
                if self.company_snapshot_version is None
                else _positive(self.company_snapshot_version)
            ),
            company_snapshot_hash=(
                None if self.company_snapshot_hash is None else _sha256(self.company_snapshot_hash)
            ),
            company_freshness=_text(self.company_freshness, 32),
            company_industry=_text(self.company_industry, 200),
        )

    def identity_values(self) -> dict[str, object]:
        return {
            "application_decision_id": str(self.application_decision_id),
            "candidate_profile": [
                str(self.candidate_profile_id),
                self.candidate_profile_version,
            ],
            "company_snapshot": (
                None
                if self.company_snapshot_id is None
                else [
                    str(self.company_snapshot_id),
                    self.company_snapshot_version,
                    self.company_snapshot_hash,
                    self.company_freshness,
                    self.company_industry,
                ]
            ),
            "decision_case_id": str(self.decision_case_id),
            "job_posting": [str(self.job_posting_id), self.job_posting_version],
            "report": [str(self.report_id), self.report_version],
            "resume_variant": [
                str(self.resume_variant_id),
                self.resume_variant_version,
                self.variant_content_fingerprint,
            ],
            "resume_version": [str(self.resume_version_id), self.resume_version],
        }


@dataclass(frozen=True, slots=True)
class MessageDraft:
    id: UUID
    owner_id: UUID
    version: int
    source: MessageDraftSource
    style: MessageDraftStyle
    user_note: str | None
    referral_context: str | None
    generator_version: str
    template_version: str
    generation_identity: str
    text: str
    content_fingerprint: str
    revision_type: MessageDraftRevisionType
    previous_version: int | None
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime

    @classmethod
    def generate(
        cls,
        *,
        owner_id: UUID,
        source: MessageDraftSource,
        style: MessageDraftStyle,
        user_note: str | None,
        referral_context: str | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "MessageDraft":
        normalized_source = source.normalized()
        normalized_style = _style(style)
        note = _text(user_note, MAX_USER_NOTE_LENGTH)
        referral = _text(referral_context, MAX_REFERRAL_CONTEXT_LENGTH)
        if normalized_style is MessageDraftStyle.REFERRAL and referral is None:
            raise DomainError(
                "Referral context is required",
                error_code="referral_context_required",
            )
        if normalized_style is not MessageDraftStyle.REFERRAL and referral is not None:
            raise DomainError(
                "Referral context is only valid for referral style",
                error_code="invalid_referral_context",
            )
        generation_values = {
            **normalized_source.identity_values(),
            "generator_version": MESSAGE_DRAFT_GENERATOR_VERSION,
            "referral_context": referral,
            "style": normalized_style.value,
            "template_version": MESSAGE_DRAFT_TEMPLATE_VERSION,
            "user_note": note,
        }
        identity = _digest(generation_values)
        text = _render(normalized_source, normalized_style, note, referral)
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            version=1,
            source=normalized_source,
            style=normalized_style,
            user_note=note,
            referral_context=referral,
            generator_version=MESSAGE_DRAFT_GENERATOR_VERSION,
            template_version=MESSAGE_DRAFT_TEMPLATE_VERSION,
            generation_identity=identity,
            text=text,
            content_fingerprint=_content_fingerprint(identity, 1, text),
            revision_type=MessageDraftRevisionType.GENERATED,
            previous_version=None,
            idempotency_key=_text(idempotency_key, 255, required=True) or "",
            request_fingerprint=identity,
            created_at=_utc(now),
        )

    def edit(
        self,
        *,
        text: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> "MessageDraft":
        value = _plain_text(text, MAX_DRAFT_TEXT_LENGTH, required=True) or ""
        next_version = self.version + 1
        request_fingerprint = edit_request_fingerprint(self.id, self.version, value)
        return replace(
            self,
            version=next_version,
            text=value,
            content_fingerprint=_content_fingerprint(self.generation_identity, next_version, value),
            revision_type=MessageDraftRevisionType.EDITED,
            previous_version=self.version,
            idempotency_key=_text(idempotency_key, 255, required=True) or "",
            request_fingerprint=request_fingerprint,
            created_at=_utc(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        draft_id: UUID,
        owner_id: UUID,
        version: int,
        source: MessageDraftSource,
        style: MessageDraftStyle,
        user_note: str | None,
        referral_context: str | None,
        generator_version: str,
        template_version: str,
        generation_identity: str,
        text: str,
        content_fingerprint: str,
        revision_type: MessageDraftRevisionType,
        previous_version: int | None,
        idempotency_key: str,
        request_fingerprint: str,
        created_at: datetime,
    ) -> "MessageDraft":
        normalized_version = _positive(version)
        normalized_text = _plain_text(text, MAX_DRAFT_TEXT_LENGTH, required=True) or ""
        normalized_revision = MessageDraftRevisionType(revision_type)
        if (normalized_version == 1) != (normalized_revision is MessageDraftRevisionType.GENERATED):
            raise DomainError(
                "Message draft revision type is invalid",
                error_code="invalid_message_draft_revision",
            )
        if normalized_version == 1:
            if previous_version is not None:
                raise DomainError(
                    "Generated draft cannot have a previous version",
                    error_code="invalid_message_draft_revision",
                )
        elif previous_version != normalized_version - 1:
            raise DomainError(
                "Message draft previous version is invalid",
                error_code="invalid_message_draft_revision",
            )
        identity = _sha256(generation_identity)
        fingerprint = _sha256(content_fingerprint)
        if fingerprint != _content_fingerprint(identity, normalized_version, normalized_text):
            raise DomainError(
                "Message draft content fingerprint is invalid",
                error_code="invalid_message_draft_fingerprint",
            )
        return cls(
            id=draft_id,
            owner_id=owner_id,
            version=normalized_version,
            source=source.normalized(),
            style=_style(style),
            user_note=_text(user_note, MAX_USER_NOTE_LENGTH),
            referral_context=_text(referral_context, MAX_REFERRAL_CONTEXT_LENGTH),
            generator_version=_text(generator_version, 100, required=True) or "",
            template_version=_text(template_version, 100, required=True) or "",
            generation_identity=identity,
            text=normalized_text,
            content_fingerprint=fingerprint,
            revision_type=normalized_revision,
            previous_version=previous_version,
            idempotency_key=_text(idempotency_key, 255, required=True) or "",
            request_fingerprint=_sha256(request_fingerprint),
            created_at=_utc(created_at),
        )


def edit_request_fingerprint(draft_id: UUID, base_version: int, text: str) -> str:
    return _digest(
        {
            "base_version": _positive(base_version),
            "draft_id": str(draft_id),
            "text": _plain_text(text, MAX_DRAFT_TEXT_LENGTH, required=True),
        }
    )


def _render(
    source: MessageDraftSource,
    style: MessageDraftStyle,
    note: str | None,
    referral: str | None,
) -> str:
    opportunity = f"{source.company_name}的{source.job_title}机会"
    if source.company_industry:
        opportunity = (
            f"{source.company_name}在{source.company_industry}领域的{source.job_title}机会"
        )
    if style is MessageDraftStyle.CONCISE:
        paragraphs = [
            f"您好，我是{source.display_name}，想申请{source.company_name}的{source.job_title}职位。岗位定制简历已准备，期待进一步沟通。"
        ]
    elif style is MessageDraftStyle.REFERRAL:
        assert referral is not None
        paragraphs = [
            f"您好，我是{source.display_name}。",
            referral,
            f"我想申请{opportunity}，岗位定制简历已准备，期待进一步沟通。",
        ]
    else:
        paragraphs = [
            f"您好，我是{source.display_name}。",
            f"我关注到{opportunity}。",
        ]
        if source.skills:
            paragraphs.append(f"我的技能包括{'、'.join(source.skills[:3])}。")
        paragraphs.append("岗位定制简历已准备，期待有机会进一步沟通。谢谢！")
    if note:
        paragraphs.append(f"补充说明：{note}")
    return "\n\n".join(paragraphs)


def _content_fingerprint(identity: str, version: int, text: str) -> str:
    return _digest({"generation_identity": identity, "text": text, "version": version})


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise DomainError("SHA-256 is invalid", error_code="invalid_message_draft_hash")
    return normalized


def _style(value: MessageDraftStyle) -> MessageDraftStyle:
    try:
        return MessageDraftStyle(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(
            "Message draft style is invalid", error_code="invalid_message_draft_style"
        ) from exc


def _unique_texts(values: tuple[str, ...], maximum_items: int, maximum: int) -> tuple[str, ...]:
    normalized = tuple(value for item in values if (value := _text(item, maximum)) is not None)
    if len(normalized) > maximum_items or len(normalized) != len(set(normalized)):
        raise DomainError(
            "Message draft source values are invalid",
            error_code="invalid_message_draft_source",
        )
    return normalized


def _plain_text(value: str | None, maximum: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise DomainError("Message draft text is required", error_code="invalid_draft_text")
        return None
    if not isinstance(value, str):
        raise DomainError("Message draft value must be text", error_code="invalid_draft_text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if (required and not normalized) or len(normalized) > maximum:
        raise DomainError("Message draft text is invalid", error_code="invalid_draft_text")
    return normalized or None


def _text(value: str | None, maximum: int, *, required: bool = False) -> str | None:
    plain = _plain_text(value, maximum, required=required)
    return None if plain is None else " ".join(plain.split())


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Version must be positive", error_code="invalid_version")
    return value


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return result.astimezone(timezone.utc)
