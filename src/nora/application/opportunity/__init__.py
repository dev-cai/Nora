"""Opportunity 岗位快照应用用例。"""

from .service import (
    CreateJobPostingCommand,
    CreateJobPostingResult,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
)

__all__ = (
    "CreateJobPostingCommand",
    "CreateJobPostingResult",
    "CreateJobPostingUseCase",
    "GetJobPostingQuery",
    "GetJobPostingUseCase",
)
