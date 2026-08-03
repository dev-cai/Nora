"""异步数据库连接和 ORM 基础设施。"""

from .base import AuditMixin, Base, OwnedByUserMixin
from .career import (
    CandidateProfileRecord,
    ResumeVersionRecord,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyResumeVersionRepository,
)
from .engine import create_database_engine, create_session_factory
from .governance import AuditEventRecord, SqlAlchemyAuditEventRepository
from .identity import SqlAlchemyUserRepository, UserRecord
from .opportunity import (
    JobPostingIdempotencyRecord,
    JobPostingRecord,
    SqlAlchemyJobPostingRepository,
)
from .repository import SqlAlchemyRepository, SqlAlchemyUserScopedRepository

__all__ = (
    "AuditMixin",
    "Base",
    "CandidateProfileRecord",
    "ResumeVersionRecord",
    "OwnedByUserMixin",
    "AuditEventRecord",
    "JobPostingIdempotencyRecord",
    "JobPostingRecord",
    "SqlAlchemyRepository",
    "SqlAlchemyAuditEventRepository",
    "SqlAlchemyCandidateProfileRepository",
    "SqlAlchemyResumeVersionRepository",
    "SqlAlchemyJobPostingRepository",
    "SqlAlchemyUserScopedRepository",
    "create_database_engine",
    "create_session_factory",
    "SqlAlchemyUserRepository",
    "UserRecord",
)
