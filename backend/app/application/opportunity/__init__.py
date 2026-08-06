"""Opportunity 岗位快照应用用例。"""

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
    "CreateJobPostingCommand",
    "CreateJobPostingResult",
    "CreateJobPostingUseCase",
    "GetJobPostingQuery",
    "GetJobPostingUseCase",
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
