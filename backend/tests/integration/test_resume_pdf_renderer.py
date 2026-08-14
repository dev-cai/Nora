"""Locked WeasyPrint determinism and resource isolation tests."""

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.domain.followup import (
    ResumePdf,
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)
from app.infrastructure.pdf_renderer import WeasyPrintResumePdfRenderer, _deny_url_fetch

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _inputs() -> tuple[ResumeVariant, TemplateDefinition, ResumePdf]:
    template = TemplateDefinition.create(
        template_id=uuid4(),
        version=1,
        name="锁定模板",
        page_size=TemplatePageSize.A4,
        density=TemplateDensity.STANDARD,
        accent=TemplateAccent.BLUE,
        section_order=("basic_information",),
        allowed_fields=("basic_information.*",),
        required_fields=("basic_information.display_name",),
        published_at=NOW,
    )
    variant = ResumeVariant.create(
        owner_id=uuid4(),
        application_decision_id=uuid4(),
        decision_case_id=uuid4(),
        job_posting_id=uuid4(),
        job_posting_version=1,
        job_requirement_snapshot_id=uuid4(),
        job_requirement_snapshot_version=1,
        resume_version_id=uuid4(),
        resume_version=1,
        template=template,
        resume_content={"basic_information": {"display_name": "Alice"}},
        title="<script>网络与文件读取测试</script>",
        blocks=(
            VariantBlock.create(
                source_path="basic_information.display_name",
                label="<img src=file:///etc/passwd>",
                value="https://evil.example/tracker.png",
            ),
        ),
        idempotency_key="renderer",
        now=NOW,
    )
    renderer = WeasyPrintResumePdfRenderer()
    pdf = ResumePdf.create(
        variant=variant,
        template=template,
        renderer_version=renderer.renderer_version,
        font_set_version=renderer.font_set_version,
        now=NOW,
    )
    return variant, template, pdf


def test_locked_renderer_produces_stable_pdf_bytes_without_loading_text_as_markup() -> None:
    variant, template, pdf = _inputs()
    renderer = WeasyPrintResumePdfRenderer()

    first = renderer.render(variant, template, pdf.generation_identity).data
    second = renderer.render(variant, template, pdf.generation_identity).data

    assert first.startswith(b"%PDF-1.7")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert renderer.renderer_version.startswith("weasyprint-69.0-pango-1.56.3-sde-1767225600-")
    assert renderer.font_set_version == "noto-cjk-20240730-v1"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/script.js",
        "file:///etc/passwd",
        "data:text/html,<script>alert(1)</script>",
    ],
)
def test_renderer_url_fetcher_rejects_every_resource_scheme(url: str) -> None:
    with pytest.raises(ValueError, match="External resources are disabled"):
        _deny_url_fetch(url)
