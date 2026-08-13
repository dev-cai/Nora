"""Opportunity 岗位快照应用用例。"""

from .company import (
    AppendCompanySnapshotCommand,
    CompanySnapshotUseCases,
    CompanySnapshotValues,
    CreateCompanySnapshotCommand,
    GetCompanySnapshotQuery,
)
from .requirements import (
    GetJobRequirementSnapshotQuery,
    GetJobRequirementSnapshotUseCase,
    ListJobRequirementSnapshotsQuery,
    ListJobRequirementSnapshotsResult,
    ListJobRequirementSnapshotsUseCase,
    SaveJobRequirementSnapshotCommand,
    SaveJobRequirementSnapshotResult,
    SaveJobRequirementSnapshotUseCase,
)
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
    "AppendCompanySnapshotCommand",
    "CompanySnapshotUseCases",
    "CompanySnapshotValues",
    "CreateCompanySnapshotCommand",
    "CreateJobPostingCommand",
    "CreateJobPostingResult",
    "CreateJobPostingUseCase",
    "GetJobPostingQuery",
    "GetJobPostingUseCase",
    "GetCompanySnapshotQuery",
    "GetJobRequirementSnapshotQuery",
    "GetJobRequirementSnapshotUseCase",
    "ListJobPostingsQuery",
    "ListJobPostingsResult",
    "ListJobPostingsUseCase",
    "ListJobRequirementSnapshotsQuery",
    "ListJobRequirementSnapshotsResult",
    "ListJobRequirementSnapshotsUseCase",
    "SaveJobRequirementSnapshotCommand",
    "SaveJobRequirementSnapshotResult",
    "SaveJobRequirementSnapshotUseCase",
)
