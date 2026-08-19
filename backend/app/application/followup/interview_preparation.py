"""Generate versioned interview preparation from fixed case inputs and retrieval evidence."""

from dataclasses import dataclass
from uuid import UUID

from app.application.knowledge import KnowledgeRagService
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.decision import DecisionReport
from app.domain.followup import (
    InterviewCase,
    InterviewPreparation,
    PreparationCitation,
    PreparationPriority,
    PreparationTopic,
)
from app.ports.career import ResumeVersionRepository
from app.ports.decision import (
    DecisionCaseRepository,
    DecisionReportRepository,
    JobFitAnalysisRepository,
)
from app.ports.followup import ApplicationRecordRepository, InterviewCaseRepository
from app.ports.interview_preparation import InterviewPreparationRepository
from app.ports.opportunity import JobPostingRepository

GENERATOR_VERSION = "interview-preparation-v1"
PROMPT_VERSION = "interview-preparation-rag-v1"


@dataclass(frozen=True, slots=True)
class GenerateInterviewPreparationResult:
    preparation: InterviewPreparation
    replayed: bool


class InterviewPreparationUseCases:
    def __init__(
        self,
        preparations: InterviewPreparationRepository,
        interviews: InterviewCaseRepository,
        applications: ApplicationRecordRepository,
        decision_cases: DecisionCaseRepository,
        reports: DecisionReportRepository,
        resumes: ResumeVersionRepository,
        jobs: JobPostingRepository,
        job_fit: JobFitAnalysisRepository,
        rag: KnowledgeRagService,
    ) -> None:
        self.preparations = preparations
        self.interviews = interviews
        self.applications = applications
        self.decision_cases = decision_cases
        self.reports = reports
        self.resumes = resumes
        self.jobs = jobs
        self.job_fit = job_fit
        self.rag = rag

    async def generate(
        self, owner_id: UUID, interview_case_id: UUID
    ) -> GenerateInterviewPreparationResult:
        interview = await self.interviews.get_latest(interview_case_id)
        if interview is None or interview.owner_id != owner_id:
            raise ApplicationError("Interview not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        application = await self.applications.get_by_id(interview.application_record_id)
        if application is None or application.owner_id != owner_id:
            raise ApplicationError(
                "Application record not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        decision_case = await self.decision_cases.get_by_id(application.decision_case_id)
        if decision_case is None or decision_case.owner_id != owner_id:
            raise ApplicationError(
                "Decision inputs not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        report = await self._latest_report(owner_id, decision_case.id)
        resume = await self.resumes.get_by_identity(
            decision_case.resume_version_id, decision_case.resume_version
        )
        job = await self.jobs.get_by_id(decision_case.job_posting_id)
        if (
            resume is None
            or resume.owner_id != owner_id
            or job is None
            or job.owner_id != owner_id
            or job.version != decision_case.job_posting_version
        ):
            raise ApplicationError(
                "Interview preparation inputs not found",
                error_code=ErrorCode.ENTITY_NOT_FOUND,
            )
        fit = None if report is None else await self.job_fit.get_for_report(report.id)
        fit_risks = [] if fit is None else [item.text for item in fit.critical_gaps]
        project_risks = [] if fit is None else [item.text for item in fit.project_deep_dive_risks]
        query = (
            f"面试准备：第{interview.round_number}轮；岗位 {job.job_title}；"
            f"公司 {job.company_name}；岗位摘要 {job.text_summary}；简历 {resume.title}；"
            f"高风险缺口 {'；'.join(fit_risks) or 'unknown'}；"
            f"项目风险 {'；'.join(project_risks) or 'unknown'}"
        )
        answer = await self.rag.ask(owner_id, query, limit=5)
        citations = tuple(
            PreparationCitation(
                item.chunk_id,
                item.source_id,
                item.source_version,
                item.locator,
                item.excerpt,
                item.score,
            )
            for item in answer.citations
        )
        citation_ids = tuple(item.citation_id for item in citations)
        grounded = answer.status == "grounded"
        evidence_text = answer.answer if grounded else "unknown"
        project_reason = "；".join(project_risks) or evidence_text
        resume_reason = "；".join(fit_risks) or evidence_text
        topics = (
            PreparationTopic(
                "project-deep-dive",
                "项目深挖",
                PreparationPriority.HIGH,
                project_reason
                if grounded or project_risks
                else "unknown：当前检索没有足够证据确认项目细节",
                45,
                "grounded" if grounded else "unknown",
                "准备一个可核验的项目背景、你的具体贡献、关键取舍和结果；没有证据时按通用建议准备。",
                citation_ids,
            ),
            PreparationTopic(
                "technical-foundations",
                "技术栈与基础",
                PreparationPriority.MEDIUM,
                evidence_text if grounded else "unknown：当前检索没有足够证据确认技术栈重点",
                30,
                "grounded" if grounded else "unknown",
                "围绕岗位和简历中出现的技术栈准备核心概念、边界条件与故障排查；没有证据时使用通用基础题清单。",
                citation_ids,
            ),
            PreparationTopic(
                "resume-risks",
                "简历风险与反问",
                PreparationPriority.MEDIUM,
                resume_reason
                if grounded or fit_risks
                else "unknown：当前检索没有足够证据确认简历风险",
                20,
                "grounded" if grounded else "unknown",
                "准备 60 秒自我介绍、经历中的空白或夸大风险，以及 2 个针对团队目标的反问；"
                "没有证据时按通用建议准备。",
                citation_ids,
            ),
        )
        preparation = InterviewPreparation.publish(
            owner_id=owner_id,
            interview_case_id=interview.id,
            interview_case_version=interview.version,
            application_record_id=application.id,
            decision_case_id=decision_case.id,
            decision_report_id=None if report is None else report.id,
            decision_report_version=None if report is None else report.version,
            version=await self.preparations.next_version(interview.id),
            generator_version=GENERATOR_VERSION,
            prompt_version=PROMPT_VERSION,
            topics=topics,
            citations=citations,
        )
        stored = await self.preparations.add(preparation)
        await self.preparations.commit()
        return GenerateInterviewPreparationResult(stored, False)

    async def get_latest(self, owner_id: UUID, interview_case_id: UUID) -> InterviewPreparation:
        await self._require_interview(owner_id, interview_case_id)
        value = await self.preparations.get_latest(interview_case_id)
        if value is None:
            raise ApplicationError(
                "Interview preparation not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return value

    async def get_version(
        self, owner_id: UUID, interview_case_id: UUID, version: int
    ) -> InterviewPreparation:
        await self._require_interview(owner_id, interview_case_id)
        value = await self.preparations.get_version(interview_case_id, version)
        if value is None:
            raise ApplicationError(
                "Interview preparation not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return value

    async def list_versions(
        self, owner_id: UUID, interview_case_id: UUID
    ) -> list[InterviewPreparation]:
        await self._require_interview(owner_id, interview_case_id)
        return await self.preparations.list_versions(interview_case_id)

    async def _require_interview(self, owner_id: UUID, interview_case_id: UUID) -> InterviewCase:
        value = await self.interviews.get_latest(interview_case_id)
        if value is None or value.owner_id != owner_id:
            raise ApplicationError("Interview not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return value

    async def _latest_report(self, owner_id: UUID, decision_case_id: UUID) -> DecisionReport | None:
        reports = await self.reports.list_for_case(decision_case_id)
        return reports[-1] if reports and reports[-1].owner_id == owner_id else None
