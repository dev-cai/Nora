"""Application & Follow-up repository contracts."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.followup import (
    ApplicationDecision,
    ResumePdf,
    ResumeVariant,
    TemplateDefinition,
)


class ApplicationDecisionRepository(Protocol):
    async def add(self, decision: ApplicationDecision) -> ApplicationDecision: ...

    async def get_by_report_id(self, report_id: UUID) -> ApplicationDecision | None: ...

    async def get_by_id(self, decision_id: UUID) -> ApplicationDecision | None: ...

    async def get_by_idempotency_key(self, key: str) -> ApplicationDecision | None: ...

    async def commit(self) -> None: ...


class TemplateDefinitionRepository(Protocol):
    async def list(self) -> list[TemplateDefinition]: ...

    async def get_by_identity(
        self, template_id: UUID, version: int
    ) -> TemplateDefinition | None: ...


class ResumeVariantRepository(Protocol):
    async def add(self, variant: ResumeVariant) -> ResumeVariant: ...

    async def get_by_id(self, variant_id: UUID) -> ResumeVariant | None: ...

    async def get_by_idempotency_key(self, key: str) -> ResumeVariant | None: ...

    async def list(self, *, offset: int, limit: int) -> list[ResumeVariant]: ...

    async def count(self) -> int: ...

    async def commit(self) -> None: ...


class ResumePdfRepository(Protocol):
    async def add(self, pdf: ResumePdf) -> ResumePdf: ...

    async def update(self, pdf: ResumePdf) -> ResumePdf: ...

    async def get_by_id(self, pdf_id: UUID) -> ResumePdf | None: ...

    async def get_by_generation_identity(self, identity: str) -> ResumePdf | None: ...

    async def get_latest_by_variant(self, variant_id: UUID) -> ResumePdf | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RenderedPdf:
    data: bytes


class ResumePdfRenderer(Protocol):
    @property
    def renderer_version(self) -> str: ...

    @property
    def font_set_version(self) -> str: ...

    def render(
        self,
        variant: ResumeVariant,
        template: TemplateDefinition,
        generation_identity: str,
    ) -> RenderedPdf: ...
