"""Authenticated declarative template and immutable ResumeVariant API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.application.followup import (
    CreateResumeVariantCommand,
    ListResumeVariantsQuery,
    ResumeVariantUseCases,
)
from app.apps.api.dependencies import (
    get_application_decision_repository,
    get_current_user,
    get_decision_case_repository,
    get_resume_variant_repository,
    get_resume_version_repository,
    get_template_definition_repository,
)
from app.domain.followup import ResumeVariant, TemplateDefinition, VariantBlock
from app.domain.identity import User
from app.ports.career import ResumeVersionRepository
from app.ports.decision import DecisionCaseRepository
from app.ports.followup import (
    ApplicationDecisionRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)

template_router = APIRouter(prefix="/templates", tags=["templates"])
variant_router = APIRouter(prefix="/resume-variants", tags=["resume-variants"])


class TemplateDefinitionResponse(BaseModel):
    id: UUID
    version: int
    name: str
    page_size: str
    density: str
    accent: str
    section_order: list[str]
    allowed_fields: list[str]
    required_fields: list[str]
    definition_hash: str
    published_at: datetime

    @classmethod
    def from_domain(cls, value: TemplateDefinition) -> "TemplateDefinitionResponse":
        return cls(
            id=value.id,
            version=value.version,
            name=value.name,
            page_size=value.page_size.value,
            density=value.density.value,
            accent=value.accent.value,
            section_order=list(value.section_order),
            allowed_fields=list(value.allowed_fields),
            required_fields=list(value.required_fields),
            definition_hash=value.definition_hash,
            published_at=value.published_at,
        )


class VariantBlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=3, max_length=500)
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=4_000)


class CreateResumeVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_decision_id: UUID
    template_id: UUID
    template_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    blocks: list[VariantBlockRequest] = Field(min_length=1, max_length=100)


class VariantBlockResponse(BaseModel):
    source_path: str
    label: str
    value: str


class ResumeVariantResponse(BaseModel):
    id: UUID
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
    blocks: list[VariantBlockResponse]
    generator_version: str
    content_fingerprint: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: ResumeVariant) -> "ResumeVariantResponse":
        return cls(
            id=value.id,
            version=value.version,
            application_decision_id=value.application_decision_id,
            decision_case_id=value.decision_case_id,
            job_posting_id=value.job_posting_id,
            job_posting_version=value.job_posting_version,
            job_requirement_snapshot_id=value.job_requirement_snapshot_id,
            job_requirement_snapshot_version=value.job_requirement_snapshot_version,
            resume_version_id=value.resume_version_id,
            resume_version=value.resume_version,
            template_id=value.template_id,
            template_version=value.template_version,
            title=value.title,
            blocks=[
                VariantBlockResponse.model_validate(item, from_attributes=True)
                for item in value.blocks
            ],
            generator_version=value.generator_version,
            content_fingerprint=value.content_fingerprint,
            created_at=value.created_at,
        )


class ResumeVariantListResponse(BaseModel):
    items: list[ResumeVariantResponse]
    page: int
    page_size: int
    total: int


def _use_cases(
    variants: ResumeVariantRepository,
    templates: TemplateDefinitionRepository,
    decisions: ApplicationDecisionRepository,
    cases: DecisionCaseRepository,
    resumes: ResumeVersionRepository,
) -> ResumeVariantUseCases:
    return ResumeVariantUseCases(variants, templates, decisions, cases, resumes)


@template_router.get("", response_model=list[TemplateDefinitionResponse])
async def list_templates(
    _user: User = Depends(get_current_user),
    repository: TemplateDefinitionRepository = Depends(get_template_definition_repository),
) -> list[TemplateDefinitionResponse]:
    return [TemplateDefinitionResponse.from_domain(item) for item in await repository.list()]


@template_router.get("/{template_id}/versions/{version}", response_model=TemplateDefinitionResponse)
async def get_template(
    template_id: UUID,
    version: int,
    _user: User = Depends(get_current_user),
    repository: TemplateDefinitionRepository = Depends(get_template_definition_repository),
) -> TemplateDefinitionResponse:
    from app.domain.base.exceptions import ApplicationError

    template = await repository.get_by_identity(template_id, version)
    if template is None:
        raise ApplicationError("Template not found", error_code="entity_not_found")
    return TemplateDefinitionResponse.from_domain(template)


@variant_router.post("", response_model=ResumeVariantResponse, status_code=status.HTTP_201_CREATED)
async def create_resume_variant(
    payload: CreateResumeVariantRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVariantResponse:
    result = await _use_cases(variants, templates, decisions, cases, resumes).create(
        CreateResumeVariantCommand(
            owner_id=user.id,
            application_decision_id=payload.application_decision_id,
            template_id=payload.template_id,
            template_version=payload.template_version,
            title=payload.title,
            blocks=tuple(VariantBlock.create(**item.model_dump()) for item in payload.blocks),
            idempotency_key=idempotency_key,
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ResumeVariantResponse.from_domain(result.variant)


@variant_router.get("", response_model=ResumeVariantListResponse)
async def list_resume_variants(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: User = Depends(get_current_user),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVariantListResponse:
    result = await _use_cases(variants, templates, decisions, cases, resumes).list(
        ListResumeVariantsQuery(owner_id=user.id, page=page, page_size=page_size)
    )
    return ResumeVariantListResponse(
        items=[ResumeVariantResponse.from_domain(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@variant_router.get("/{variant_id}", response_model=ResumeVariantResponse)
async def get_resume_variant(
    variant_id: UUID,
    user: User = Depends(get_current_user),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    decisions: ApplicationDecisionRepository = Depends(get_application_decision_repository),
    cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
) -> ResumeVariantResponse:
    value = await _use_cases(variants, templates, decisions, cases, resumes).get(
        user.id, variant_id
    )
    return ResumeVariantResponse.from_domain(value)
