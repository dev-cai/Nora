"""Declarative template and immutable ResumeVariant contract tests."""

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.followup import CreateResumeVariantCommand, ResumeVariantUseCases
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import ResumeVersion
from app.domain.decision import DecisionCase
from app.domain.followup import (
    ApplicationDecision,
    ApplicationDecisionStatus,
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)

NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def test_template_definition_rejects_executable_or_unknown_fields() -> None:
    with pytest.raises(DomainError) as script:
        _template(allowed_fields=("skills.*.<script>",))
    assert script.value.error_code == "invalid_template_field"

    with pytest.raises(DomainError) as external_resource:
        _template(allowed_fields=("external_resources.url",))
    assert external_resource.value.error_code == "invalid_template_field"


def test_resume_variant_fingerprint_includes_order_edits_and_fixed_versions() -> None:
    inputs = _inputs()
    first = _variant(inputs=inputs, blocks=_blocks())
    replay = _variant(inputs=inputs, blocks=_blocks())
    reordered = _variant(inputs=inputs, blocks=tuple(reversed(_blocks())))
    edited = _variant(
        inputs=inputs,
        blocks=(
            _blocks()[0],
            VariantBlock.create(
                source_path="skills.skill-1.name", label="核心技能", value="Python / FastAPI"
            ),
        ),
    )

    assert first.content_fingerprint == replay.content_fingerprint
    assert reordered.content_fingerprint != first.content_fingerprint
    assert edited.content_fingerprint != first.content_fingerprint
    assert first.job_posting_version == 2
    assert first.job_requirement_snapshot_version == 3
    assert first.resume_version == 4
    assert first.template_version == 1


def test_resume_variant_rejects_missing_or_unavailable_source_fields() -> None:
    inputs = _inputs()
    with pytest.raises(DomainError) as required:
        _variant(inputs=inputs, blocks=(_blocks()[1],))
    assert required.value.error_code == "required_variant_field"

    with pytest.raises(DomainError) as unavailable:
        _variant(
            inputs=inputs,
            blocks=(
                _blocks()[0],
                VariantBlock.create(source_path="skills.skill-2.name", label="技能", value="Rust"),
            ),
        )
    assert unavailable.value.error_code == "invalid_variant_field"


@pytest.mark.asyncio
async def test_resume_variant_use_case_replays_and_preserves_exact_inputs() -> None:
    inputs = _inputs()
    variants = MemoryVariantRepository()
    use_case = _use_case(inputs, variants)
    command = CreateResumeVariantCommand(
        owner_id=inputs["owner_id"],
        application_decision_id=inputs["decision"].id,
        template_id=inputs["template"].id,
        template_version=inputs["template"].version,
        title="后端岗位定制版",
        blocks=_blocks(),
        idempotency_key="variant-1",
    )

    first = await use_case.create(command)
    replay = await use_case.create(command)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.variant.id == first.variant.id
    assert first.variant.decision_case_id == inputs["case"].id
    assert first.variant.resume_version_id == inputs["resume"].id
    assert variants.commits == 1

    with pytest.raises(ApplicationError) as conflict:
        await use_case.create(
            replace(
                command,
                blocks=(
                    _blocks()[0],
                    VariantBlock.create(
                        source_path="skills.skill-1.name",
                        label="核心技能",
                        value="Edited",
                    ),
                ),
            )
        )
    assert conflict.value.error_code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_resume_variant_use_case_rejects_skip_and_foreign_decisions() -> None:
    inputs = _inputs(status=ApplicationDecisionStatus.SKIP)
    command = CreateResumeVariantCommand(
        owner_id=inputs["owner_id"],
        application_decision_id=inputs["decision"].id,
        template_id=inputs["template"].id,
        template_version=1,
        title="不应创建",
        blocks=_blocks(),
        idempotency_key="variant-skip",
    )
    with pytest.raises(ApplicationError) as skip:
        await _use_case(inputs, MemoryVariantRepository()).create(command)
    assert skip.value.error_code == "entity_not_found"

    with pytest.raises(ApplicationError) as foreign:
        await _use_case(_inputs(), MemoryVariantRepository()).create(
            replace(command, owner_id=uuid4(), idempotency_key="foreign")
        )
    assert foreign.value.error_code == "entity_not_found"


class MemoryVariantRepository:
    def __init__(self) -> None:
        self.items: list[ResumeVariant] = []
        self.commits = 0

    async def add(self, value: ResumeVariant) -> ResumeVariant:
        self.items.append(value)
        return value

    async def get_by_id(self, variant_id: UUID) -> ResumeVariant | None:
        return next((item for item in self.items if item.id == variant_id), None)

    async def get_by_idempotency_key(self, key: str) -> ResumeVariant | None:
        return next((item for item in self.items if item.idempotency_key == key), None)

    async def list(self, *, offset: int, limit: int) -> list[ResumeVariant]:
        return self.items[offset : offset + limit]

    async def count(self) -> int:
        return len(self.items)

    async def commit(self) -> None:
        self.commits += 1


class LookupRepository:
    def __init__(self, value: object) -> None:
        self.value = value

    async def get_by_id(self, entity_id: UUID) -> object | None:
        return self.value if getattr(self.value, "id") == entity_id else None

    async def get_by_identity(self, entity_id: UUID, version: int) -> object | None:
        return (
            self.value
            if getattr(self.value, "id") == entity_id and getattr(self.value, "version") == version
            else None
        )


def _use_case(
    inputs: dict[str, object], variants: MemoryVariantRepository
) -> ResumeVariantUseCases:
    return ResumeVariantUseCases(
        variants,
        LookupRepository(inputs["template"]),
        LookupRepository(inputs["decision"]),
        LookupRepository(inputs["case"]),
        LookupRepository(inputs["resume"]),
    )


def _template(
    *, allowed_fields: tuple[str, ...] = ("basic_information.*", "skills.*.*")
) -> TemplateDefinition:
    return TemplateDefinition.create(
        template_id=UUID("159f9891-54ac-4f19-9eb3-9c67db60c8d1"),
        version=1,
        name="清晰单栏",
        page_size=TemplatePageSize.A4,
        density=TemplateDensity.STANDARD,
        accent=TemplateAccent.NEUTRAL,
        section_order=("basic_information", "skills"),
        allowed_fields=allowed_fields,
        required_fields=("basic_information.display_name",),
        published_at=NOW,
    )


def _blocks() -> tuple[VariantBlock, ...]:
    return (
        VariantBlock.create(
            source_path="basic_information.display_name", label="姓名", value="Alice"
        ),
        VariantBlock.create(source_path="skills.skill-1.name", label="核心技能", value="Python"),
    )


def _inputs(
    status: ApplicationDecisionStatus = ApplicationDecisionStatus.APPLY,
) -> dict[str, object]:
    owner_id = uuid4()
    resume = ResumeVersion.restore(
        resume_id=uuid4(),
        owner_id=owner_id,
        version=4,
        candidate_profile_id=uuid4(),
        profile_version=2,
        title="Backend",
        content={
            "basic_information": {"display_name": "Alice"},
            "skills": [{"id": "skill-1", "name": "Python"}],
        },
        published_at=NOW,
    )
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=uuid4(),
        job_posting_version=2,
        job_requirement_snapshot_id=uuid4(),
        job_requirement_snapshot_version=3,
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
        status=status,
        reason="不匹配" if status is ApplicationDecisionStatus.SKIP else None,
        idempotency_key="decision",
        now=NOW,
    )
    return {
        "owner_id": owner_id,
        "resume": resume,
        "case": decision_case,
        "decision": decision,
        "template": _template(),
    }


def _variant(*, inputs: dict[str, object], blocks: tuple[VariantBlock, ...]) -> ResumeVariant:
    owner_id = inputs["owner_id"]
    decision = inputs["decision"]
    decision_case = inputs["case"]
    resume = inputs["resume"]
    template = inputs["template"]
    assert isinstance(owner_id, UUID)
    assert isinstance(decision, ApplicationDecision)
    assert isinstance(decision_case, DecisionCase)
    assert isinstance(resume, ResumeVersion)
    assert isinstance(template, TemplateDefinition)
    return ResumeVariant.create(
        owner_id=owner_id,
        application_decision_id=decision.id,
        decision_case_id=decision_case.id,
        job_posting_id=decision_case.job_posting_id,
        job_posting_version=decision_case.job_posting_version,
        job_requirement_snapshot_id=decision_case.job_requirement_snapshot_id,
        job_requirement_snapshot_version=decision_case.job_requirement_snapshot_version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        template=template,
        resume_content=resume.content,
        title="后端岗位定制版",
        blocks=blocks,
        idempotency_key="variant",
        now=NOW,
    )
