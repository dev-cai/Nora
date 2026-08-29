"""Agent Runtime composition root for the API-process orchestration adapter."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime import AgentRuntimeService
from app.agent_runtime.tools import AgentToolInput, AgentToolOutput, build_tool_registry
from app.application.followup import InterviewPreparationUseCases
from app.application.knowledge import KnowledgeRagService
from app.apps.api.dependencies.career import get_resume_version_repository
from app.apps.api.dependencies.common import get_current_user, get_session, get_settings
from app.apps.api.dependencies.decision import (
    get_decision_case_repository,
    get_decision_report_repository,
    get_job_fit_analysis_repository,
)
from app.apps.api.dependencies.followup import (
    get_application_record_repository,
    get_interview_case_repository,
    get_interview_preparation_repository,
)
from app.apps.api.dependencies.knowledge import get_knowledge_rag_service
from app.apps.api.dependencies.opportunity import get_job_posting_repository
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import SqlAlchemyAgentRuntimeRepository
from app.ports.career import ResumeVersionRepository
from app.ports.decision import (
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.followup import (
    ApplicationRecordRepository,
    InterviewCaseRepository,
)
from app.ports.interview_preparation import InterviewPreparationRepository
from app.ports.opportunity import JobPostingRepository


def get_agent_runtime_service(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    rag: KnowledgeRagService = Depends(get_knowledge_rag_service),
    preparations: InterviewPreparationRepository = Depends(get_interview_preparation_repository),
    interviews: InterviewCaseRepository = Depends(get_interview_case_repository),
    applications: ApplicationRecordRepository = Depends(get_application_record_repository),
    decision_cases: DecisionCaseRepository = Depends(get_decision_case_repository),
    reports: DecisionReportRepository = Depends(get_decision_report_repository),
    resumes: ResumeVersionRepository = Depends(get_resume_version_repository),
    jobs: JobPostingRepository = Depends(get_job_posting_repository),
    job_fit: JobFitAnalysisRepository = Depends(get_job_fit_analysis_repository),
) -> AgentRuntimeService:
    preparation_use_cases = InterviewPreparationUseCases(
        preparations,
        interviews,
        applications,
        decision_cases,
        reports,
        resumes,
        jobs,
        job_fit,
        rag,
    )

    async def context(value: AgentToolInput) -> AgentToolOutput:
        if value.job_posting_id is None:
            return AgentToolOutput(
                result_ref=f"goal:{user.id}",
                summary=f"已确认目标：{value.user_goal[:500]}",
                target_type="user_goal",
                target_id=user.id,
                payload={"user_goal": value.user_goal},
            )
        job = await jobs.get_by_id(value.job_posting_id)
        if job is None or job.owner_id != user.id:
            from app.domain.base.exceptions import ApplicationError, ErrorCode

            raise ApplicationError("Job posting not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return AgentToolOutput(
            result_ref=f"job-posting:{job.id}:v{job.version}",
            summary=job.text_summary,
            target_type="job_posting",
            target_id=job.id,
            target_version=job.version,
            payload={"job_title": job.job_title, "company_name": job.company_name},
        )

    async def retrieve(value: AgentToolInput) -> AgentToolOutput:
        answer = await rag.ask(user.id, value.user_goal, source_id=value.source_id, limit=5)
        return AgentToolOutput(
            result_ref=f"rag:{user.id}",
            summary=answer.answer[:4_000],
            target_type="knowledge_evidence",
            payload={
                "status": answer.status,
                "citations": [str(item.chunk_id) for item in answer.citations],
            },
        )

    async def compute_job_fit_placeholder(value: AgentToolInput) -> AgentToolOutput:
        return AgentToolOutput(
            result_ref=f"tool-input:{user.id}",
            summary=("已校验 typed 输入；当前 COMPUTE 占位只返回结果引用，不写入业务事实。"),
            target_type="compute_result",
            target_id=value.job_posting_id,
            target_version=None,
            payload={"job_posting_id": str(value.job_posting_id) if value.job_posting_id else None},
        )

    async def prepare(value: AgentToolInput) -> AgentToolOutput:
        if value.interview_case_id is None:
            from app.domain.base.exceptions import ApplicationError, ErrorCode

            raise ApplicationError(
                "Interview case is required", error_code=ErrorCode.VALIDATION_ERROR
            )
        result = await preparation_use_cases.generate(user.id, value.interview_case_id)
        preparation = result.preparation
        return AgentToolOutput(
            result_ref=f"interview-preparation:{preparation.id}:v{preparation.version}",
            summary=f"已生成第 {preparation.version} 版面试准备计划",
            target_type="interview_preparation",
            target_id=preparation.id,
            target_version=preparation.version,
            payload={"interview_case_id": str(value.interview_case_id)},
        )

    async def application_status(value: AgentToolInput) -> AgentToolOutput:
        if value.application_record_id is None:
            from app.domain.base.exceptions import ApplicationError, ErrorCode

            raise ApplicationError(
                "Application record is required", error_code=ErrorCode.VALIDATION_ERROR
            )
        record = await applications.get_by_id(value.application_record_id)
        if record is None or record.owner_id != user.id:
            from app.domain.base.exceptions import ApplicationError, ErrorCode

            raise ApplicationError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return AgentToolOutput(
            result_ref=f"application-record:{record.id}:v{record.version}",
            summary=f"投递状态：{record.status.value}",
            target_type="application_record",
            target_id=record.id,
            target_version=record.version,
            payload={"status": record.status.value},
        )

    handlers = {
        "get_opportunity_context": context,
        "analyze_job_fit": compute_job_fit_placeholder,
        "retrieve_knowledge": retrieve,
        "prepare_interview": prepare,
        "get_application_status": application_status,
    }
    return AgentRuntimeService(
        SqlAlchemyAgentRuntimeRepository(session, user.id),
        dict(build_tool_registry(handlers)),
        checkpoint_database_url=settings.database_url,
    )


__all__ = ("get_agent_runtime_service",)
