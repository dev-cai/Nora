"""Opportunity 岗位快照应用用例。"""

from .service import (
    CreateJobPostingCommand,
    CreateJobPostingResult,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
    ListJobPostingsQuery,
    ListJobPostingsResult,
    ListJobPostingsUseCase,
)

__all__ = (
    "CreateJobPostingCommand",
    "CreateJobPostingResult",
    "CreateJobPostingUseCase",
    "GetJobPostingQuery",
    "GetJobPostingUseCase",
    "ListJobPostingsQuery",
    "ListJobPostingsResult",
    "ListJobPostingsUseCase",
)
