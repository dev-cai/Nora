"""Career Profile 领域对象。"""

from .candidate_profile import (
    CandidateProfile,
    ConfirmationStatus,
    ProfileSourceType,
)
from .resume_version import MAX_RESUME_TITLE_LENGTH, ResumeVersion

__all__ = (
    "MAX_RESUME_TITLE_LENGTH",
    "CandidateProfile",
    "ConfirmationStatus",
    "ProfileSourceType",
    "ResumeVersion",
)
