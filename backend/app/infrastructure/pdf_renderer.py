"""Locked, network-free WeasyPrint adapter for deterministic resume PDFs."""

import os
from html import escape
from importlib.metadata import version
from typing import NoReturn

from app.domain.base.exceptions import InfrastructureError
from app.domain.followup import ResumeVariant, TemplateDefinition
from app.ports.followup import RenderedPdf

PDF_ADAPTER_VERSION = "nora-resume-pdf-v1"
PANGO_VERSION = "1.56.3"
FONT_SET_VERSION = "noto-cjk-20240730-v1"
SOURCE_DATE_EPOCH = "1767225600"


class WeasyPrintResumePdfRenderer:
    @property
    def renderer_version(self) -> str:
        return (
            f"weasyprint-{version('weasyprint')}-pango-{PANGO_VERSION}-"
            f"sde-{SOURCE_DATE_EPOCH}-{PDF_ADAPTER_VERSION}"
        )

    @property
    def font_set_version(self) -> str:
        return FONT_SET_VERSION

    def render(
        self,
        variant: ResumeVariant,
        template: TemplateDefinition,
        generation_identity: str,
    ) -> RenderedPdf:
        if (variant.template_id, variant.template_version) != (template.id, template.version):
            raise InfrastructureError(
                "Resume PDF template mismatch", error_code="pdf_render_failed"
            )
        try:
            os.environ["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
            from weasyprint import HTML

            output = HTML(
                string=_document(variant, template),
                url_fetcher=_deny_url_fetch,
            ).write_pdf(
                pdf_identifier=bytes.fromhex(generation_identity),
                pdf_version="1.7",
                custom_metadata=False,
                pdf_forms=False,
                pdf_tags=False,
                full_fonts=False,
                hinting=False,
            )
        except Exception as exc:
            raise InfrastructureError(
                "Resume PDF rendering failed", error_code="pdf_render_failed"
            ) from exc
        if not output.startswith(b"%PDF-") or len(output) < 100:
            raise InfrastructureError(
                "Resume PDF output is invalid", error_code="pdf_render_failed"
            )
        return RenderedPdf(data=output)


def _deny_url_fetch(
    url: str,
    timeout: int = 10,
    ssl_context: object | None = None,
) -> NoReturn:
    del timeout, ssl_context
    raise ValueError(f"External resources are disabled: {url[:20]}")


def _document(variant: ResumeVariant, template: TemplateDefinition) -> str:
    page_size = "A4" if template.page_size.value == "a4" else "Letter"
    compact = template.density.value == "compact"
    accent = "#175f45" if template.accent.value == "neutral" else "#1759a6"
    padding = "7mm 10mm" if compact else "11mm 14mm"
    block_gap = "3mm" if compact else "5mm"
    blocks = "".join(
        (
            '<section class="resume-block">'
            f"<h2>{escape(block.label)}</h2>"
            f"<p>{escape(block.value)}</p>"
            "</section>"
        )
        for block in variant.blocks
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{escape(variant.title)}</title>"
        "<style>"
        f"@page {{ size: {page_size}; margin: 0; }}"
        "* { box-sizing: border-box; }"
        "html, body { margin: 0; padding: 0; color: #17231d; "
        'font-family: "Noto Sans CJK SC", "Noto Sans CJK", sans-serif; }'
        f"main {{ min-height: 100vh; padding: {padding}; }}"
        f"h1 {{ margin: 0 0 7mm; color: {accent}; font-size: 22pt; line-height: 1.2; }}"
        f".resume-block {{ break-inside: avoid; margin: 0 0 {block_gap}; }}"
        f".resume-block h2 {{ margin: 0 0 1.2mm; color: {accent}; "
        "font-size: 9pt; font-weight: 700; text-transform: uppercase; }"
        ".resume-block p { margin: 0; font-size: 10.5pt; line-height: 1.55; "
        "white-space: pre-wrap; overflow-wrap: anywhere; }"
        ".footer { position: fixed; right: 10mm; bottom: 5mm; color: #78847d; "
        "font-size: 7pt; }"
        "</style></head><body><main>"
        f"<h1>{escape(variant.title)}</h1>{blocks}"
        '<div class="footer">Nora · deterministic resume</div>'
        "</main></body></html>"
    )
