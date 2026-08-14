"""Deterministic Resume PDF domain and application contracts."""

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.followup import GenerateResumePdfCommand, ResumePdfService
from app.application.knowledge import ArtifactDownload
from app.domain.base.exceptions import ApplicationError
from app.domain.followup import (
    ResumePdf,
    ResumePdfStatus,
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)
from app.domain.knowledge import Artifact, ArtifactKind
from app.ports.followup import RenderedPdf

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


class MemoryPdfs:
    def __init__(self) -> None:
        self.values: dict[UUID, ResumePdf] = {}

    async def add(self, value: ResumePdf) -> ResumePdf:
        self.values[value.id] = value
        return value

    async def update(self, value: ResumePdf) -> ResumePdf:
        self.values[value.id] = value
        return value

    async def get_by_id(self, pdf_id: UUID) -> ResumePdf | None:
        return self.values.get(pdf_id)

    async def get_by_generation_identity(self, identity: str) -> ResumePdf | None:
        return next(
            (value for value in self.values.values() if value.generation_identity == identity),
            None,
        )

    async def get_latest_by_variant(self, variant_id: UUID) -> ResumePdf | None:
        return next(
            (value for value in self.values.values() if value.resume_variant_id == variant_id),
            None,
        )

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class Lookup:
    def __init__(self, value: object) -> None:
        self.value = value

    async def get_by_id(self, entity_id: UUID):
        return self.value if getattr(self.value, "id") == entity_id else None

    async def get_by_identity(self, entity_id: UUID, version: int):
        return (
            self.value
            if (getattr(self.value, "id"), getattr(self.value, "version")) == (entity_id, version)
            else None
        )


class DeterministicRenderer:
    renderer_version = "weasyprint-69.0-pango-1.56.3-test"
    font_set_version = "noto-cjk-test"

    def __init__(self) -> None:
        self.calls = 0

    def render(self, variant, template, generation_identity: str) -> RenderedPdf:
        del variant, template
        self.calls += 1
        return RenderedPdf(data=b"%PDF-1.7\n" + generation_identity.encode() + b"\n%%EOF")


class MemoryArtifactService:
    def __init__(self) -> None:
        self.failures = 0
        self.artifacts: dict[UUID, tuple[Artifact, bytes]] = {}
        self.by_key: dict[str, UUID] = {}

    async def upload(self, command) -> Artifact:
        if self.failures:
            self.failures -= 1
            raise ApplicationError(
                "Artifact storage is unavailable", error_code="artifact_storage_unavailable"
            )
        existing_id = self.by_key.get(command.idempotency_key)
        if existing_id is not None:
            return self.artifacts[existing_id][0]
        pending = Artifact.pending(
            owner_id=command.owner_id,
            kind=ArtifactKind.GENERATED,
            content_type=command.content_type,
            size_bytes=len(command.data),
            sha256=hashlib.sha256(command.data).hexdigest(),
            idempotency_key=command.idempotency_key,
            generator_version=command.generator_version,
            generation_identity=command.generation_identity,
            now=NOW,
        )
        artifact = pending.publish(f"{command.owner_id}/{pending.id}/1/pdf")
        self.by_key[command.idempotency_key] = artifact.id
        self.artifacts[artifact.id] = (artifact, command.data)
        return artifact

    async def download(self, owner_id: UUID, artifact_id: UUID) -> ArtifactDownload:
        artifact, data = self.artifacts[artifact_id]
        if artifact.owner_id != owner_id:
            raise ApplicationError("Artifact not found", error_code="entity_not_found")
        return ArtifactDownload(artifact=artifact, data=data)


def _inputs() -> tuple[ResumeVariant, TemplateDefinition]:
    owner_id = uuid4()
    template = TemplateDefinition.create(
        template_id=uuid4(),
        version=2,
        name="清晰单栏",
        page_size=TemplatePageSize.A4,
        density=TemplateDensity.STANDARD,
        accent=TemplateAccent.NEUTRAL,
        section_order=("basic_information",),
        allowed_fields=("basic_information.*",),
        required_fields=("basic_information.display_name",),
        published_at=NOW,
    )
    variant = ResumeVariant.create(
        owner_id=owner_id,
        application_decision_id=uuid4(),
        decision_case_id=uuid4(),
        job_posting_id=uuid4(),
        job_posting_version=3,
        job_requirement_snapshot_id=uuid4(),
        job_requirement_snapshot_version=4,
        resume_version_id=uuid4(),
        resume_version=5,
        template=template,
        resume_content={"basic_information": {"display_name": "Alice"}},
        title="岗位定制版",
        blocks=(
            VariantBlock.create(
                source_path="basic_information.display_name",
                label="姓名",
                value="Alice",
            ),
        ),
        idempotency_key="variant",
        now=NOW,
    )
    return variant, template


def _service(
    pdfs: MemoryPdfs,
    renderer: DeterministicRenderer,
    artifacts: MemoryArtifactService,
) -> tuple[ResumePdfService, ResumeVariant]:
    variant, template = _inputs()
    return (
        ResumePdfService(
            pdfs,
            Lookup(variant),
            Lookup(template),
            renderer,
            artifacts,  # type: ignore[arg-type]
        ),
        variant,
    )


@pytest.mark.asyncio
async def test_resume_pdf_generation_is_versioned_idempotent_and_downloadable() -> None:
    pdfs = MemoryPdfs()
    renderer = DeterministicRenderer()
    artifacts = MemoryArtifactService()
    service, variant = _service(pdfs, renderer, artifacts)
    command = GenerateResumePdfCommand(variant.owner_id, variant.id)

    first = await service.generate(command)
    replay = await service.generate(command)
    downloaded = await service.download(variant.owner_id, first.pdf.id)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.pdf.id == first.pdf.id
    assert first.pdf.status is ResumePdfStatus.AVAILABLE
    assert first.pdf.resume_variant_version == variant.version
    assert first.pdf.variant_content_fingerprint == variant.content_fingerprint
    assert first.pdf.artifact_sha256 == hashlib.sha256(downloaded.data).hexdigest()
    assert renderer.calls == 1


@pytest.mark.asyncio
async def test_resume_pdf_storage_failure_is_recorded_and_retry_recovers_same_identity() -> None:
    pdfs = MemoryPdfs()
    renderer = DeterministicRenderer()
    artifacts = MemoryArtifactService()
    artifacts.failures = 1
    service, variant = _service(pdfs, renderer, artifacts)
    command = GenerateResumePdfCommand(variant.owner_id, variant.id)

    with pytest.raises(ApplicationError) as failed:
        await service.generate(command)
    assert failed.value.error_code == "artifact_storage_unavailable"
    failed_pdf = await service.get_latest(variant.owner_id, variant.id)
    assert failed_pdf is not None
    assert failed_pdf.status is ResumePdfStatus.FAILED

    recovered = await service.generate(command)
    assert recovered.pdf.id == failed_pdf.id
    assert recovered.pdf.generation_identity == failed_pdf.generation_identity
    assert recovered.pdf.status is ResumePdfStatus.AVAILABLE


def test_resume_pdf_identity_changes_with_locked_render_inputs() -> None:
    variant, template = _inputs()
    first = ResumePdf.create(
        variant=variant,
        template=template,
        renderer_version="renderer-1",
        font_set_version="fonts-1",
        now=NOW,
    )
    changed_renderer = ResumePdf.create(
        variant=variant,
        template=template,
        renderer_version="renderer-2",
        font_set_version="fonts-1",
        now=NOW,
    )
    changed_fonts = ResumePdf.create(
        variant=variant,
        template=template,
        renderer_version="renderer-1",
        font_set_version="fonts-2",
        now=NOW,
    )

    assert len(first.generation_identity) == 64
    identities = {
        first.generation_identity,
        changed_renderer.generation_identity,
        changed_fonts.generation_identity,
    }
    assert len(identities) == 3
