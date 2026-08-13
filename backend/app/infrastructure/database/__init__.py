"""异步数据库连接和 ORM 基础设施。"""

from .base import AuditMixin, Base, OwnedByUserMixin
from .career import (
    CandidateProfileRecord,
    ResumeVersionRecord,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyResumeVersionRepository,
)
from .decision import (
    DecisionCaseRecord,
    DecisionReportRecord,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
)
from .engine import create_database_engine, create_session_factory
from .followup import ApplicationDecisionRecord, SqlAlchemyApplicationDecisionRepository
from .governance import AuditEventRecord, SqlAlchemyAuditEventRepository
from .identity import SqlAlchemyUserRepository, UserRecord
from .knowledge import (
    ArtifactRecord,
    SourceDocumentRecord,
    SqlAlchemyArtifactRepository,
    SqlAlchemySourceDocumentRepository,
)
from .opportunity import (
    JobPostingIdempotencyRecord,
    JobPostingRecord,
    JobRequirementSnapshotRecord,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
)
from .repository import SqlAlchemyRepository, SqlAlchemyUserScopedRepository

__all__ = (
    "AuditMixin",
    "Base",
    "CandidateProfileRecord",
    "DecisionCaseRecord",
    "DecisionReportRecord",
    "ResumeVersionRecord",
    "OwnedByUserMixin",
    "AuditEventRecord",
    "ApplicationDecisionRecord",
    "ArtifactRecord",
    "JobPostingIdempotencyRecord",
    "JobPostingRecord",
    "JobRequirementSnapshotRecord",
    "SourceDocumentRecord",
    "SqlAlchemyRepository",
    "SqlAlchemyAuditEventRepository",
    "SqlAlchemyApplicationDecisionRepository",
    "SqlAlchemyArtifactRepository",
    "SqlAlchemyCandidateProfileRepository",
    "SqlAlchemyDecisionCaseRepository",
    "SqlAlchemyDecisionReportRepository",
    "SqlAlchemyResumeVersionRepository",
    "SqlAlchemySourceDocumentRepository",
    "SqlAlchemyJobPostingRepository",
    "SqlAlchemyJobRequirementSnapshotRepository",
    "SqlAlchemyUserScopedRepository",
    "create_database_engine",
    "create_session_factory",
    "SqlAlchemyUserRepository",
    "UserRecord",
)
