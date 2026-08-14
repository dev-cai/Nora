"""Generate and read deterministic Resume PDF Artifacts."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.application.knowledge import ArtifactDownload, ArtifactService, UploadArtifactCommand
from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.followup import PDF_CONTENT_TYPE, ResumePdf, ResumePdfStatus
from app.domain.knowledge import ArtifactKind, ArtifactStatus
from app.ports.followup import (
    ResumePdfRenderer,
    ResumePdfRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)


@dataclass(frozen=True, slots=True)
class GenerateResumePdfCommand:
    owner_id: UUID
    resume_variant_id: UUID


@dataclass(frozen=True, slots=True)
class GenerateResumePdfResult:
    pdf: ResumePdf
    replayed: bool


@dataclass(frozen=True, slots=True)
class ResumePdfDownload:
    pdf: ResumePdf
    data: bytes


class ResumePdfService:
    def __init__(
        self,
        pdfs: ResumePdfRepository,
        variants: ResumeVariantRepository,
        templates: TemplateDefinitionRepository,
        renderer: ResumePdfRenderer,
        artifacts: ArtifactService,
    ) -> None:
        self.pdfs = pdfs
        self.variants = variants
        self.templates = templates
        self.renderer = renderer
        self.artifacts = artifacts

    async def generate(self, command: GenerateResumePdfCommand) -> GenerateResumePdfResult:
        variant = await self.variants.get_by_id(command.resume_variant_id)
        if variant is None or variant.owner_id != command.owner_id:
            raise ApplicationError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        template = await self.templates.get_by_identity(
            variant.template_id, variant.template_version
        )
        if template is None:
            raise ApplicationError(
                "Resume template not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        candidate = ResumePdf.create(
            variant=variant,
            template=template,
            renderer_version=self.renderer.renderer_version,
            font_set_version=self.renderer.font_set_version,
        )
        pdf = await self.pdfs.get_by_generation_identity(candidate.generation_identity)
        if pdf is not None and pdf.status is ResumePdfStatus.AVAILABLE:
            return GenerateResumePdfResult(pdf=pdf, replayed=True)
        if pdf is None:
            try:
                pdf = await self.pdfs.add(candidate)
                await self.pdfs.commit()
            except InfrastructureError as exc:
                if exc.error_code != "resume_pdf_conflict":
                    raise
                pdf = await self.pdfs.get_by_generation_identity(candidate.generation_identity)
                if pdf is None:
                    raise InfrastructureError(
                        "Could not recover Resume PDF",
                        error_code=ErrorCode.RESUME_PDF_PERSISTENCE_FAILED,
                    ) from exc
        else:
            pdf = pdf.retry()
            await self.pdfs.update(pdf)
            await self.pdfs.commit()

        try:
            rendered = await asyncio.to_thread(
                self.renderer.render,
                variant,
                template,
                pdf.generation_identity,
            )
            artifact = await self.artifacts.upload(
                UploadArtifactCommand(
                    owner_id=command.owner_id,
                    kind=ArtifactKind.GENERATED,
                    content_type=PDF_CONTENT_TYPE,
                    data=rendered.data,
                    idempotency_key=f"resume-pdf:{pdf.generation_identity}",
                    generator_version=pdf.renderer_version,
                    generation_identity=pdf.generation_identity,
                )
            )
            if (
                artifact.status is not ArtifactStatus.AVAILABLE
                or artifact.kind is not ArtifactKind.GENERATED
                or artifact.generation_identity != pdf.generation_identity
                or artifact.generator_version != pdf.renderer_version
            ):
                raise ApplicationError(
                    "Resume PDF Artifact is invalid",
                    error_code=ErrorCode.PDF_GENERATION_FAILED,
                )
            available = pdf.publish(
                artifact_id=artifact.id,
                artifact_version=artifact.version,
                artifact_sha256=artifact.sha256,
                artifact_size_bytes=artifact.size_bytes,
            )
            await self.pdfs.update(available)
            await self.pdfs.commit()
            return GenerateResumePdfResult(pdf=available, replayed=False)
        except Exception as exc:
            await self.pdfs.rollback()
            try:
                await self.pdfs.update(pdf.fail())
                await self.pdfs.commit()
            except Exception:
                await self.pdfs.rollback()
            if isinstance(exc, ApplicationError):
                raise
            raise ApplicationError(
                "Resume PDF generation failed", error_code=ErrorCode.PDF_GENERATION_FAILED
            ) from exc

    async def get(self, owner_id: UUID, pdf_id: UUID) -> ResumePdf:
        pdf = await self.pdfs.get_by_id(pdf_id)
        if pdf is None or pdf.owner_id != owner_id:
            raise ApplicationError("Resume PDF not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return pdf

    async def get_latest(self, owner_id: UUID, variant_id: UUID) -> ResumePdf | None:
        variant = await self.variants.get_by_id(variant_id)
        if variant is None or variant.owner_id != owner_id:
            raise ApplicationError(
                "Resume variant not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return await self.pdfs.get_latest_by_variant(variant_id)

    async def download(self, owner_id: UUID, pdf_id: UUID) -> ResumePdfDownload:
        pdf = await self.get(owner_id, pdf_id)
        if pdf.status is not ResumePdfStatus.AVAILABLE or pdf.artifact_id is None:
            raise ApplicationError("Resume PDF not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        result: ArtifactDownload = await self.artifacts.download(owner_id, pdf.artifact_id)
        artifact = result.artifact
        if (
            artifact.version != pdf.artifact_version
            or artifact.content_type != PDF_CONTENT_TYPE
            or artifact.sha256 != pdf.artifact_sha256
            or artifact.size_bytes != pdf.artifact_size_bytes
            or artifact.kind is not ArtifactKind.GENERATED
            or artifact.generation_identity != pdf.generation_identity
            or artifact.generator_version != pdf.renderer_version
        ):
            raise ApplicationError(
                "Resume PDF Artifact integrity check failed",
                error_code=ErrorCode.ARTIFACT_CORRUPT,
            )
        return ResumePdfDownload(pdf=pdf, data=result.data)
