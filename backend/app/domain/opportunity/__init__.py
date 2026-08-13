"""Opportunity Intelligence 领域模型。"""

from .job_posting import (
    UNKNOWN_COMPANY_NAME,
    UNKNOWN_JOB_TITLE,
    UNKNOWN_LOCATION,
    JobPosting,
    JobPostingStatus,
    JobSourceType,
)
from .job_requirement_snapshot import (
    JobRequirementSnapshot,
    RequirementConfirmationStatus,
    RequirementSourceType,
    WorkMode,
)

__all__ = (
    "CompanyFieldStatus",
    "CompanySnapshot",
    "CompanySourceReference",
    "CompanySourceTier",
    "Freshness",
    "UNKNOWN_COMPANY_NAME",
    "UNKNOWN_JOB_TITLE",
    "UNKNOWN_LOCATION",
    "JobPosting",
    "JobPostingStatus",
    "JobSourceType",
    "JobRequirementSnapshot",
    "RequirementConfirmationStatus",
    "RequirementSourceType",
    "WorkMode",
)
from .company import (
    CompanyFieldStatus,
    CompanySnapshot,
    CompanySourceReference,
    CompanySourceTier,
    Freshness,
)
