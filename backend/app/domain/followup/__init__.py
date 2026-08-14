"""Application & Follow-up domain exports."""

from .application_decision import ApplicationDecision, ApplicationDecisionStatus
from .resume_variant import (
    ResumeVariant,
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
    VariantBlock,
)

__all__ = (
    "ApplicationDecision",
    "ApplicationDecisionStatus",
    "ResumeVariant",
    "TemplateAccent",
    "TemplateDefinition",
    "TemplateDensity",
    "TemplatePageSize",
    "VariantBlock",
)
