"""Deterministic MessageDraft and append-only revision tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from app.application.followup import (
    EditMessageDraftCommand,
    GenerateMessageDraftCommand,
    MessageDraftUseCases,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import ResumeVersion
from app.domain.decision import CompanyAssessment, CompanyAssessmentStatus, DecisionCase
from app.domain.followup import (
    ApplicationDecision,
    ApplicationDecisionStatus,
    MessageDraft,
    MessageDraftRevisionType,
    MessageDraftSource,
    MessageDraftStyle,
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)
from app.domain.opportunity import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceReference,
    CompanySourceTier,
    JobPosting,
)

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def test_message_draft_styles_are_deterministic_and_referral_is_explicit() -> None:
    source = _source()
    first = MessageDraft.generate(
        owner_id=uuid4(),
        source=source,
        style=MessageDraftStyle.PROFESSIONAL,
        user_note="可在本周沟通",
        referral_context=None,
        idempotency_key="draft-1",
        now=NOW,
    )
    replay = MessageDraft.generate(
        owner_id=first.owner_id,
        source=source,
        style=MessageDraftStyle.PROFESSIONAL,
        user_note="可在本周沟通",
        referral_context=None,
        idempotency_key="draft-2",
        now=NOW,
    )

    assert first.generation_identity == replay.generation_identity
    assert first.text == replay.text
    assert "Python" in first.text
    assert "unknown" not in first.text
    assert "补充说明：可在本周沟通" in first.text

    with pytest.raises(DomainError) as missing:
        MessageDraft.generate(
            owner_id=first.owner_id,
            source=source,
            style=MessageDraftStyle.REFERRAL,
            user_note=None,
            referral_context=None,
            idempotency_key="referral",
            now=NOW,
        )
    assert missing.value.error_code == "referral_context_required"

    referral = MessageDraft.generate(
        owner_id=first.owner_id,
        source=source,
        style=MessageDraftStyle.REFERRAL,
        user_note=None,
        referral_context="经张女士建议，我来联系您。",
        idempotency_key="referral",
        now=NOW,
    )
    assert "经张女士建议" in referral.text
    assert referral.generation_identity != first.generation_identity


def test_message_draft_edit_appends_version_without_overwriting_generated_text() -> None:
    original = MessageDraft.generate(
        owner_id=uuid4(),
        source=_source(),
        style=MessageDraftStyle.CONCISE,
        user_note=None,
        referral_context=None,
        idempotency_key="draft",
        now=NOW,
    )
    edited = original.edit(
        text=f"{original.text}\n\n我可以随时开始。",
        idempotency_key="edit-1",
        now=NOW,
    )

    assert original.version == 1
    assert original.revision_type is MessageDraftRevisionType.GENERATED
    assert edited.version == 2
    assert edited.previous_version == 1
    assert edited.revision_type is MessageDraftRevisionType.EDITED
    assert edited.generation_identity == original.generation_identity
    assert edited.content_fingerprint != original.content_fingerprint
    assert "随时开始" not in original.text


def test_message_draft_rejects_company_industry_without_snapshot_identity() -> None:
    with pytest.raises(DomainError) as invalid:
        MessageDraft.generate(
            owner_id=uuid4(),
            source=replace(_source(), company_industry="Software"),
            style=MessageDraftStyle.PROFESSIONAL,
            user_note=None,
            referral_context=None,
            idempotency_key="orphan-industry",
            now=NOW,
        )

    assert invalid.value.error_code == "invalid_message_draft_source"


@pytest.mark.asyncio
async def test_message_draft_use_case_replays_generation_and_versions_edits() -> None:
    inputs = _inputs()
    drafts = MemoryDraftRepository()
    use_cases = _use_cases(inputs, drafts)
    command = GenerateMessageDraftCommand(
        owner_id=inputs["owner_id"],
        resume_variant_id=inputs["variant"].id,
        style=MessageDraftStyle.PROFESSIONAL,
        user_note=None,
        referral_context=None,
        idempotency_key="generate-1",
    )

    generated = await use_cases.generate(command)
    replay = await use_cases.generate(replace(command, idempotency_key="generate-2"))
    edited = await use_cases.edit(
        EditMessageDraftCommand(
            owner_id=inputs["owner_id"],
            draft_id=generated.draft.id,
            base_version=1,
            text=f"{generated.draft.text}\n\n期待回复。",
            idempotency_key=" edit  request ",
        )
    )
    edit_replay = await use_cases.edit(
        EditMessageDraftCommand(
            owner_id=inputs["owner_id"],
            draft_id=generated.draft.id,
            base_version=1,
            text=f"{generated.draft.text}\n\n期待回复。",
            idempotency_key=" edit  request ",
        )
    )

    assert generated.replayed is False
    assert replay.replayed is True
    assert replay.draft.id == generated.draft.id
    assert edited.draft.version == 2
    assert edited.draft.idempotency_key == "edit  request"
    assert edit_replay.replayed is True
    assert len(await drafts.list_versions(generated.draft.id)) == 2

    with pytest.raises(ApplicationError) as stale:
        await use_cases.edit(
            EditMessageDraftCommand(
                owner_id=inputs["owner_id"],
                draft_id=generated.draft.id,
                base_version=1,
                text="过期编辑",
                idempotency_key="edit-stale",
            )
        )
    assert stale.value.error_code == "message_draft_version_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("assessment_status", "industry_status", "published_at", "includes_industry"),
    [
        (
            CompanyAssessmentStatus.AVAILABLE,
            CompanyFieldStatus.CONFIRMED,
            NOW - timedelta(days=30),
            True,
        ),
        (
            CompanyAssessmentStatus.STALE,
            CompanyFieldStatus.UNCONFIRMED,
            NOW - timedelta(days=731),
            False,
        ),
        (
            CompanyAssessmentStatus.UNKNOWN,
            CompanyFieldStatus.UNCONFIRMED,
            None,
            False,
        ),
        (
            CompanyAssessmentStatus.CONFLICTED,
            CompanyFieldStatus.CONFLICTED,
            NOW - timedelta(days=30),
            False,
        ),
    ],
)
async def test_message_draft_only_renders_available_confirmed_company_industry(
    assessment_status: CompanyAssessmentStatus,
    industry_status: CompanyFieldStatus,
    published_at: datetime | None,
    includes_industry: bool,
) -> None:
    inputs = _inputs()
    source = CompanySourceReference.create(
        source_id=uuid4(),
        source_version=1,
        source_tier=CompanySourceTier.OFFICIAL,
        source_kind="manual",
        acquisition_method="user_entry",
        license_note="user supplied",
        acquired_at=NOW,
        published_at=published_at,
        content_sha256="d" * 64,
    )
    snapshot = CompanySnapshot.create(
        owner_id=inputs["owner_id"],
        company_name="Example Inc",
        size="100-499",
        size_status=(
            CompanyFieldStatus.CONFIRMED
            if assessment_status is CompanyAssessmentStatus.AVAILABLE
            else CompanyFieldStatus.UNCONFIRMED
        ),
        industry="Software",
        industry_status=industry_status,
        review_summary="公开资料摘要",
        review_status=CompanyFieldStatus.UNCONFIRMED,
        source=source,
        now=NOW,
    )
    decision = inputs["decision"]
    decision_case = inputs["case"]
    assessment = CompanyAssessment.create(
        owner_id=inputs["owner_id"],
        report_id=decision.report_id,
        report_version=decision.report_version,
        decision_case_id=decision_case.id,
        decision_case_version=1,
        company_snapshot_id=snapshot.id,
        company_snapshot_version=snapshot.version,
        status=assessment_status,
        status_reason="fixed_snapshot",
        generator_version="m4-company-assessment-v1",
        now=NOW,
    )
    use_cases = _use_cases(inputs, MemoryDraftRepository(), assessment, snapshot)

    result = await use_cases.generate(
        GenerateMessageDraftCommand(
            owner_id=inputs["owner_id"],
            resume_variant_id=inputs["variant"].id,
            style=MessageDraftStyle.PROFESSIONAL,
            user_note=None,
            referral_context=None,
            idempotency_key=f"company-{assessment_status.value}",
        )
    )

    assert result.draft.source.company_snapshot_id == snapshot.id
    assert result.draft.source.company_snapshot_version == snapshot.version
    assert result.draft.source.company_snapshot_hash == snapshot.content_sha256
    assert result.draft.source.company_freshness == snapshot.freshness.value
    assert ("Software" in result.draft.text) is includes_industry


class MemoryDraftRepository:
    def __init__(self) -> None:
        self.items: list[MessageDraft] = []

    async def add(self, value: MessageDraft) -> MessageDraft:
        self.items.append(value)
        return value

    async def get_latest(self, draft_id: UUID) -> MessageDraft | None:
        values = [item for item in self.items if item.id == draft_id]
        return max(values, key=lambda item: item.version) if values else None

    async def get_version(self, draft_id: UUID, version: int) -> MessageDraft | None:
        return next(
            (item for item in self.items if item.id == draft_id and item.version == version),
            None,
        )

    async def get_by_idempotency_key(self, key: str) -> MessageDraft | None:
        return next((item for item in self.items if item.idempotency_key == key), None)

    async def get_by_generation_identity(self, identity: str) -> MessageDraft | None:
        return next(
            (
                item
                for item in self.items
                if item.version == 1 and item.generation_identity == identity
            ),
            None,
        )

    async def get_latest_by_variant(self, variant_id: UUID) -> MessageDraft | None:
        values = [item for item in self.items if item.source.resume_variant_id == variant_id]
        return max(values, key=lambda item: (item.created_at, item.version)) if values else None

    async def list(self, *, offset: int, limit: int) -> list[MessageDraft]:
        latest = {
            item.id: max(
                (value for value in self.items if value.id == item.id),
                key=lambda value: value.version,
            )
            for item in self.items
        }
        return list(latest.values())[offset : offset + limit]

    async def list_versions(self, draft_id: UUID) -> list[MessageDraft]:
        return sorted(
            (item for item in self.items if item.id == draft_id),
            key=lambda item: item.version,
            reverse=True,
        )

    async def count(self) -> int:
        return len({item.id for item in self.items})

    async def commit(self) -> None:
        return None


class LookupRepository:
    def __init__(self, value: object | None) -> None:
        self.value = value

    async def get_by_id(self, entity_id: UUID) -> object | None:
        return self.value if self.value is not None and self.value.id == entity_id else None

    async def get_by_identity(self, entity_id: UUID, version: int) -> object | None:
        return (
            self.value
            if self.value is not None
            and self.value.id == entity_id
            and self.value.version == version
            else None
        )

    async def get_for_report(self, report_id: UUID) -> object | None:
        return (
            self.value
            if self.value is not None and getattr(self.value, "report_id", None) == report_id
            else None
        )


def _use_cases(
    inputs: dict[str, object],
    drafts: MemoryDraftRepository,
    assessment: object | None = None,
    snapshot: object | None = None,
) -> MessageDraftUseCases:
    return MessageDraftUseCases(
        drafts,
        LookupRepository(inputs["variant"]),
        LookupRepository(inputs["decision"]),
        LookupRepository(inputs["case"]),
        LookupRepository(inputs["resume"]),
        LookupRepository(inputs["job"]),
        LookupRepository(assessment),
        LookupRepository(snapshot),
    )


def _source() -> MessageDraftSource:
    return MessageDraftSource(
        application_decision_id=uuid4(),
        report_id=uuid4(),
        report_version=1,
        decision_case_id=uuid4(),
        resume_variant_id=uuid4(),
        resume_variant_version=1,
        variant_content_fingerprint="a" * 64,
        candidate_profile_id=uuid4(),
        candidate_profile_version=2,
        resume_version_id=uuid4(),
        resume_version=3,
        job_posting_id=uuid4(),
        job_posting_version=1,
        display_name="Alice",
        company_name="Example Inc",
        job_title="后端工程师",
        skills=("Python", "FastAPI"),
    )


def _inputs() -> dict[str, object]:
    owner_id = uuid4()
    job = JobPosting.create(
        owner_id=owner_id,
        jd_text="负责后端 API 开发",
        job_title="后端工程师",
        company_name="Example Inc",
        location="上海",
        now=NOW,
    )
    resume = ResumeVersion.restore(
        resume_id=uuid4(),
        owner_id=owner_id,
        version=2,
        candidate_profile_id=uuid4(),
        profile_version=3,
        title="后端简历",
        content={
            "basic_information": {"display_name": "Alice"},
            "skills": [{"id": "skill-1", "name": "Python"}],
        },
        published_at=NOW,
    )
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=job.id,
        job_posting_version=job.version,
        job_requirement_snapshot_id=uuid4(),
        job_requirement_snapshot_version=1,
        candidate_profile_id=resume.candidate_profile_id,
        candidate_profile_version=resume.profile_version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        rule_set_version="m3-rules-v1",
        now=NOW,
    )
    decision = ApplicationDecision.create(
        owner_id=owner_id,
        actor_id=owner_id,
        report_id=uuid4(),
        report_version=1,
        decision_case_id=decision_case.id,
        resume_version_id=resume.id,
        resume_version=resume.version,
        status=ApplicationDecisionStatus.APPLY,
        reason=None,
        idempotency_key="decision",
        now=NOW,
    )
    template = TemplateDefinition.create(
        template_id=uuid4(),
        version=1,
        name="清晰单栏",
        page_size=TemplatePageSize.A4,
        density=TemplateDensity.STANDARD,
        accent=TemplateAccent.NEUTRAL,
        section_order=("basic_information", "skills"),
        allowed_fields=("basic_information.*", "skills.*.*"),
        required_fields=("basic_information.display_name",),
        published_at=NOW,
    )
    variant = ResumeVariant.create(
        owner_id=owner_id,
        application_decision_id=decision.id,
        decision_case_id=decision_case.id,
        job_posting_id=job.id,
        job_posting_version=job.version,
        job_requirement_snapshot_id=decision_case.job_requirement_snapshot_id,
        job_requirement_snapshot_version=decision_case.job_requirement_snapshot_version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        template=template,
        resume_content=resume.content,
        title="岗位定制简历",
        blocks=(
            VariantBlock.create(
                source_path="basic_information.display_name", label="姓名", value="Alice"
            ),
        ),
        idempotency_key="variant",
        now=NOW,
    )
    return {
        "owner_id": owner_id,
        "job": job,
        "resume": resume,
        "case": decision_case,
        "decision": decision,
        "variant": variant,
    }
