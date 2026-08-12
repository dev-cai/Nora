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
    "JobPostingIdempotencyRecord",
    "JobPostingRecord",
    "JobRequirementSnapshotRecord",
    "SqlAlchemyRepository",
    "SqlAlchemyAuditEventRepository",
    "SqlAlchemyApplicationDecisionRepository",
    "SqlAlchemyCandidateProfileRepository",
    "SqlAlchemyDecisionCaseRepository",
    "SqlAlchemyDecisionReportRepository",
    "SqlAlchemyResumeVersionRepository",
    "SqlAlchemyJobPostingRepository",
    "SqlAlchemyJobRequirementSnapshotRepository",
    "SqlAlchemyUserScopedRepository",
    "create_database_engine",
    "create_session_factory",
    "SqlAlchemyUserRepository",
    "UserRecord",
)
