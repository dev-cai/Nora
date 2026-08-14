"""Authenticated deterministic Resume PDF API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel

from app.application.followup import GenerateResumePdfCommand, ResumePdfService
from app.application.knowledge import ArtifactService
from app.apps.api.dependencies import (
    get_artifact_repository,
    get_artifact_storage,
    get_audit_event_repository,
    get_current_user,
    get_resume_pdf_renderer,
    get_resume_pdf_repository,
    get_resume_variant_repository,
    get_source_document_repository,
    get_template_definition_repository,
)
from app.domain.followup import ResumePdf, ResumePdfStatus
from app.domain.identity import User
from app.ports.followup import (
    ResumePdfRenderer,
    ResumePdfRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import ArtifactRepository, ArtifactStorage, SourceDocumentRepository

router = APIRouter(tags=["resume-pdfs"])


class ResumePdfResponse(BaseModel):
    id: UUID
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
    def from_domain(cls, value: ResumePdf) -> "ResumePdfResponse":
        return cls.model_validate(value, from_attributes=True)


def _service(
    request: Request,
    pdfs: ResumePdfRepository,
    variants: ResumeVariantRepository,
    templates: TemplateDefinitionRepository,
    renderer: ResumePdfRenderer,
    artifacts: ArtifactRepository,
    sources: SourceDocumentRepository,
    storage: ArtifactStorage,
    audit_events: AuditEventRepository,
) -> ResumePdfService:
    settings = request.app.state.settings
    artifact_service = ArtifactService(
        artifacts,
        sources,
        storage,
        audit_events,
        max_size_bytes=settings.artifact_max_size_bytes,
        allowed_content_types=settings.allowed_artifact_content_types,
    )
    return ResumePdfService(pdfs, variants, templates, renderer, artifact_service)


@router.post(
    "/resume-variants/{variant_id}/pdf",
    response_model=ResumePdfResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_resume_pdf(
    request: Request,
    variant_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    renderer: ResumePdfRenderer = Depends(get_resume_pdf_renderer),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ResumePdfResponse:
    result = await _service(
        request,
        pdfs,
        variants,
        templates,
        renderer,
        artifacts,
        sources,
        storage,
        audit_events,
    ).generate(GenerateResumePdfCommand(owner_id=user.id, resume_variant_id=variant_id))
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ResumePdfResponse.from_domain(result.pdf)


@router.get("/resume-variants/{variant_id}/pdf", response_model=ResumePdfResponse)
async def get_latest_resume_pdf(
    request: Request,
    variant_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    renderer: ResumePdfRenderer = Depends(get_resume_pdf_renderer),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ResumePdfResponse | Response:
    value = await _service(
        request,
        pdfs,
        variants,
        templates,
        renderer,
        artifacts,
        sources,
        storage,
        audit_events,
    ).get_latest(user.id, variant_id)
    if value is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return ResumePdfResponse.from_domain(value)


@router.get("/resume-pdfs/{pdf_id}", response_model=ResumePdfResponse)
async def get_resume_pdf(
    request: Request,
    pdf_id: UUID,
    user: User = Depends(get_current_user),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    renderer: ResumePdfRenderer = Depends(get_resume_pdf_renderer),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> ResumePdfResponse:
    value = await _service(
        request,
        pdfs,
        variants,
        templates,
        renderer,
        artifacts,
        sources,
        storage,
        audit_events,
    ).get(user.id, pdf_id)
    return ResumePdfResponse.from_domain(value)


@router.get("/resume-pdfs/{pdf_id}/content")
async def download_resume_pdf(
    request: Request,
    pdf_id: UUID,
    download: Annotated[bool, Query()] = True,
    user: User = Depends(get_current_user),
    pdfs: ResumePdfRepository = Depends(get_resume_pdf_repository),
    variants: ResumeVariantRepository = Depends(get_resume_variant_repository),
    templates: TemplateDefinitionRepository = Depends(get_template_definition_repository),
    renderer: ResumePdfRenderer = Depends(get_resume_pdf_renderer),
    artifacts: ArtifactRepository = Depends(get_artifact_repository),
    sources: SourceDocumentRepository = Depends(get_source_document_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    audit_events: AuditEventRepository = Depends(get_audit_event_repository),
) -> Response:
    result = await _service(
        request,
        pdfs,
        variants,
        templates,
        renderer,
        artifacts,
        sources,
        storage,
        audit_events,
    ).download(user.id, pdf_id)
    disposition = "attachment" if download else "inline"
    filename = f"nora-resume-{result.pdf.id}.pdf"
    return Response(
        content=result.data,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Content-Length": str(len(result.data)),
            "X-Content-Type-Options": "nosniff",
        },
    )
