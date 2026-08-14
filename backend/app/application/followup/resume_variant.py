"""Create and read immutable ResumeVariant records from explicit apply decisions."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.followup import (
    ApplicationDecisionStatus,
    ResumeVariant,
    VariantBlock,
)
from app.ports.career import ResumeVersionRepository
from app.ports.decision import DecisionCaseRepository
from app.ports.followup import (
    ApplicationDecisionRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)


@dataclass(frozen=True, slots=True)
class CreateResumeVariantCommand:
    owner_id: UUID
    application_decision_id: UUID
    template_id: UUID
    template_version: int
    title: str
    blocks: tuple[VariantBlock, ...]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CreateResumeVariantResult:
    variant: ResumeVariant
    replayed: bool


@dataclass(frozen=True, slots=True)
class ListResumeVariantsQuery:
    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListResumeVariantsResult:
    items: tuple[ResumeVariant, ...]
    page: int
    page_size: int
    total: int


class ResumeVariantUseCases:
    def __init__(
        self,
        variants: ResumeVariantRepository,
        templates: TemplateDefinitionRepository,
        decisions: ApplicationDecisionRepository,
        cases: DecisionCaseRepository,
        resumes: ResumeVersionRepository,
    ) -> None:
        self.variants = variants
        self.templates = templates
        self.decisions = decisions
        self.cases = cases
        self.resumes = resumes

    async def create(self, command: CreateResumeVariantCommand) -> CreateResumeVariantResult:
        existing = await self.variants.get_by_idempotency_key(command.idempotency_key.strip())
        decision = await self.decisions.get_by_id(command.application_decision_id)
        if (
            decision is None
            or decision.owner_id != command.owner_id
            or decision.status is not ApplicationDecisionStatus.APPLY
        ):
            raise ApplicationError("Apply decision not found", error_code="entity_not_found")
        decision_case = await self.cases.get_by_id(decision.decision_case_id)
        resume = await self.resumes.get_by_identity(
            decision.resume_version_id, decision.resume_version
        )
        template = await self.templates.get_by_identity(
            command.template_id, command.template_version
        )
        if (
            decision_case is None
            or decision_case.owner_id != command.owner_id
            or resume is None
            or resume.owner_id != command.owner_id
            or template is None
        ):
            raise ApplicationError("Resume variant input not found", error_code="entity_not_found")
        candidate = ResumeVariant.create(
            owner_id=command.owner_id,
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
            title=command.title,
            blocks=command.blocks,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            return _replay(existing, candidate)
        try:
            stored = await self.variants.add(candidate)
            await self.variants.commit()
        except InfrastructureError as exc:
            if exc.error_code != "resume_variant_key_taken":
                raise
            existing = await self.variants.get_by_idempotency_key(candidate.idempotency_key)
            if existing is None:
                raise InfrastructureError(
                    "Could not recover resume variant",
                    error_code="resume_variant_persistence_failed",
                ) from exc
            return _replay(existing, candidate)
        return CreateResumeVariantResult(variant=stored, replayed=False)

    async def get(self, owner_id: UUID, variant_id: UUID) -> ResumeVariant:
        variant = await self.variants.get_by_id(variant_id)
        if variant is None or variant.owner_id != owner_id:
            raise ApplicationError("Resume variant not found", error_code="entity_not_found")
        return variant

    async def list(self, query: ListResumeVariantsQuery) -> ListResumeVariantsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError("Pagination is invalid", error_code="invalid_pagination")
        return ListResumeVariantsResult(
            items=tuple(
                await self.variants.list(
                    offset=(query.page - 1) * query.page_size, limit=query.page_size
                )
            ),
            page=query.page,
            page_size=query.page_size,
            total=await self.variants.count(),
        )


def _replay(existing: ResumeVariant, candidate: ResumeVariant) -> CreateResumeVariantResult:
    if existing.content_fingerprint != candidate.content_fingerprint:
        raise ApplicationError(
            "Idempotency key was already used with different content",
            error_code="idempotency_conflict",
        )
    return CreateResumeVariantResult(variant=existing, replayed=True)
