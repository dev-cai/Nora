"""异步数据库连接和 ORM 基础设施。"""

from .base import AuditMixin, Base, OwnedByUserMixin
from .career import (
    CandidateProfileRecord,
    ResumeVersionRecord,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyResumeVersionRepository,
)
from .decision import (
    CompanyAssessmentRecord,
    DecisionCaseRecord,
    DecisionReportRecord,
    SqlAlchemyCompanyAssessmentRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
)
from .engine import create_database_engine, create_session_factory
from .followup import (
    ApplicationDecisionRecord,
    ResumePdfRecord,
    ResumeVariantRecord,
    SqlAlchemyApplicationDecisionRepository,
    SqlAlchemyResumePdfRepository,
    SqlAlchemyResumeVariantRepository,
    SqlAlchemyTemplateDefinitionRepository,
    TemplateDefinitionRecord,
)
from .governance import AuditEventRecord, SqlAlchemyAuditEventRepository
from .identity import SqlAlchemyUserRepository, UserRecord
from .knowledge import (
    ArtifactRecord,
    SourceDocumentRecord,
    SqlAlchemyArtifactRepository,
    SqlAlchemySourceDocumentRepository,
)
from .opportunity import (
    CompanySnapshotRecord,
    JobPostingIdempotencyRecord,
    JobPostingRecord,
    JobRequirementSnapshotRecord,
    SqlAlchemyCompanySnapshotRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
)
from .repository import SqlAlchemyRepository, SqlAlchemyUserScopedRepository

__all__ = (
    "AuditMixin",
    "Base",
    "CandidateProfileRecord",
    "CompanyAssessmentRecord",
    "CompanySnapshotRecord",
    "DecisionCaseRecord",
    "DecisionReportRecord",
    "ResumeVersionRecord",
    "OwnedByUserMixin",
    "AuditEventRecord",
    "ApplicationDecisionRecord",
    "ResumePdfRecord",
    "ResumeVariantRecord",
    "TemplateDefinitionRecord",
    "ArtifactRecord",
    "JobPostingIdempotencyRecord",
    "JobPostingRecord",
    "JobRequirementSnapshotRecord",
    "SourceDocumentRecord",
    "SqlAlchemyRepository",
    "SqlAlchemyAuditEventRepository",
    "SqlAlchemyApplicationDecisionRepository",
    "SqlAlchemyResumePdfRepository",
    "SqlAlchemyResumeVariantRepository",
    "SqlAlchemyTemplateDefinitionRepository",
    "SqlAlchemyArtifactRepository",
    "SqlAlchemyCandidateProfileRepository",
    "SqlAlchemyCompanyAssessmentRepository",
    "SqlAlchemyCompanySnapshotRepository",
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
