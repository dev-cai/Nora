"""Application & Follow-up domain exports."""

from .application_decision import ApplicationDecision, ApplicationDecisionStatus
from .message_draft import (
    MAX_DRAFT_TEXT_LENGTH,
    MAX_REFERRAL_CONTEXT_LENGTH,
    MAX_USER_NOTE_LENGTH,
    MESSAGE_DRAFT_GENERATOR_VERSION,
    MESSAGE_DRAFT_TEMPLATE_VERSION,
    MessageDraft,
    MessageDraftRevisionType,
    MessageDraftSource,
    MessageDraftStyle,
    edit_request_fingerprint,
)
from .resume_pdf import PDF_CONTENT_TYPE, ResumePdf, ResumePdfStatus
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
    "MAX_DRAFT_TEXT_LENGTH",
    "MAX_REFERRAL_CONTEXT_LENGTH",
    "MAX_USER_NOTE_LENGTH",
    "MESSAGE_DRAFT_GENERATOR_VERSION",
    "MESSAGE_DRAFT_TEMPLATE_VERSION",
    "MessageDraft",
    "MessageDraftRevisionType",
    "MessageDraftSource",
    "MessageDraftStyle",
    "PDF_CONTENT_TYPE",
    "ResumePdf",
    "ResumePdfStatus",
    "ResumeVariant",
    "TemplateAccent",
    "TemplateDefinition",
    "TemplateDensity",
    "TemplatePageSize",
    "VariantBlock",
    "edit_request_fingerprint",
)
