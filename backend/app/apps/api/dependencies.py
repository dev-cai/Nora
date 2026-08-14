"""API 依赖：数据库会话和认证上下文。"""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.identity import IdentityService
from app.domain.base.exceptions import NoraError
from app.domain.identity import User
from app.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer
from app.infrastructure.database import (
    SqlAlchemyApplicationDecisionRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyCompanyAssessmentRepository,
    SqlAlchemyCompanySnapshotRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyDecisionReportRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
    SqlAlchemyMessageDraftRepository,
    SqlAlchemyResumePdfRepository,
    SqlAlchemyResumeVariantRepository,
    SqlAlchemyResumeVersionRepository,
    SqlAlchemySourceDocumentRepository,
    SqlAlchemyTemplateDefinitionRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.jd_fetch import JdFetchAdapter
from app.infrastructure.jd_ocr import BaiduOcrEngine, JdOcrAdapter
from app.infrastructure.object_storage import create_minio_storage
from app.infrastructure.pdf_renderer import WeasyPrintResumePdfRenderer
from app.ports.career import CandidateProfileRepository, ResumeVersionRepository
from app.ports.decision import (
    CompanyAssessmentRepository,
    DecisionCaseRepository,
    DecisionReportRepository,
)
from app.ports.followup import (
    ApplicationDecisionRepository,
    MessageDraftRepository,
    ResumePdfRenderer,
    ResumePdfRepository,
    ResumeVariantRepository,
    TemplateDefinitionRepository,
)
from app.ports.governance import AuditEventRepository
from app.ports.jd_input import JdInputPort
from app.ports.knowledge import ArtifactRepository, ArtifactStorage, SourceDocumentRepository
from app.ports.opportunity import (
    CompanySnapshotRepository,
    JobPostingRepository,
    JobRequirementSnapshotRepository,
)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """从应用生命周期创建的会话工厂提供会话。"""

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise NoraError("Database is not configured", error_code="database_unavailable")
    async with session_factory() as session:
        yield session


def get_identity_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IdentityService:
    """组装 Identity 用例及其基础设施端口。"""

    settings = request.app.state.settings
    return IdentityService(
        SqlAlchemyUserRepository(session),
        Argon2PasswordHasher(),
        JwtTokenIssuer(settings.auth_secret_key, settings.auth_access_token_minutes),
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: IdentityService = Depends(get_identity_service),
) -> User:
    """校验 Bearer Token 并返回当前用户。"""

    if credentials is None:
        raise NoraError("Authentication required", error_code="authentication_failed")
    user = await service.current_user(credentials.credentials)
    request.state.current_user = user
    return user


def get_job_posting_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobPostingRepository:
    """组装当前认证用户范围内的岗位快照 Repository。"""

    return SqlAlchemyJobPostingRepository(session, user.id)


def get_candidate_profile_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CandidateProfileRepository:
    """组装当前认证用户范围内的 CandidateProfile Repository。"""

    return SqlAlchemyCandidateProfileRepository(session, user.id)


def get_resume_version_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumeVersionRepository:
    """组装当前认证用户范围内的 ResumeVersion Repository。"""

    return SqlAlchemyResumeVersionRepository(session, user.id)


def get_job_requirement_snapshot_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobRequirementSnapshotRepository:
    """组装当前认证用户范围内的岗位要求快照 Repository。"""

    return SqlAlchemyJobRequirementSnapshotRepository(session, user.id)


def get_decision_case_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DecisionCaseRepository:
    """组装当前认证用户范围内的 DecisionCase Repository。"""

    return SqlAlchemyDecisionCaseRepository(session, user.id)


def get_decision_report_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DecisionReportRepository:
    """组装当前认证用户范围内的 DecisionReport Repository。"""

    return SqlAlchemyDecisionReportRepository(session, user.id)


def get_company_assessment_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompanyAssessmentRepository:
    return SqlAlchemyCompanyAssessmentRepository(session, user.id)


def get_company_snapshot_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompanySnapshotRepository:
    return SqlAlchemyCompanySnapshotRepository(session, user.id)


def get_application_decision_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApplicationDecisionRepository:
    """组装当前认证用户范围内的 ApplicationDecision Repository。"""

    return SqlAlchemyApplicationDecisionRepository(session, user.id)


def get_resume_variant_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumeVariantRepository:
    return SqlAlchemyResumeVariantRepository(session, user.id)


def get_message_draft_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageDraftRepository:
    return SqlAlchemyMessageDraftRepository(session, user.id)


def get_resume_pdf_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ResumePdfRepository:
    return SqlAlchemyResumePdfRepository(session, user.id)


def get_resume_pdf_renderer() -> ResumePdfRenderer:
    return WeasyPrintResumePdfRenderer()


def get_template_definition_repository(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> TemplateDefinitionRepository:
    return SqlAlchemyTemplateDefinitionRepository(session)


def get_jd_input_adapter() -> JdInputPort:
    """组装 SSRF 安全的 JD 输入 Adapter。"""

    return JdFetchAdapter()


def get_jd_ocr_adapter(request: Request) -> JdInputPort:
    """组装受限解码 + 百度 OCR 的截图 Adapter。"""

    settings = request.app.state.settings
    return JdOcrAdapter(
        engine=BaiduOcrEngine(
            api_key=settings.baidu_ocr_api_key,
            secret_key=settings.baidu_ocr_secret_key,
            endpoint=settings.baidu_ocr_endpoint,
        )
    )


def get_audit_event_repository(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> AuditEventRepository:
    """组装与业务写入共享事务的只追加审计 Repository。"""

    return SqlAlchemyAuditEventRepository(session)


def get_artifact_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ArtifactRepository:
    return SqlAlchemyArtifactRepository(session, user.id)


def get_source_document_repository(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceDocumentRepository:
    return SqlAlchemySourceDocumentRepository(session, user.id)


def get_artifact_storage(request: Request) -> ArtifactStorage:
    settings = request.app.state.settings
    return create_minio_storage(
        endpoint=settings.artifact_storage_endpoint,
        access_key=settings.artifact_storage_access_key,
        secret_key=settings.artifact_storage_secret_key,
        bucket=settings.artifact_storage_bucket,
        secure=settings.artifact_storage_secure,
    )
