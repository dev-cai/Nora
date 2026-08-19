"""AI JobFitAnalysis generation, citation and failure-boundary tests."""

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from app.application.decision import (
    GenerateJobFitAnalysisCommand,
    GenerateJobFitAnalysisUseCase,
)
from app.domain.base.exceptions import ApplicationError, DomainError, ErrorCode
from app.domain.career import CandidateProfile, ResumeVersion
from app.domain.decision import (
    RULE_SET_VERSION,
    DecisionCase,
    DecisionReport,
    JobFitAnalysis,
    RuleInputReference,
    RuleInputSource,
    RuleResult,
    RuleSetEvaluation,
    RuleStatus,
)
from app.domain.opportunity import CompanySnapshot, JobPosting, JobRequirementSnapshot
from app.infrastructure.model import FakeModelAdapter
from app.ports.model import MAX_MODEL_PROMPT_CHARS, ModelError


def _profile_fact(value: object) -> dict[str, object]:
    return {"value": value, "confirmation_status": "confirmed"}


def _requirement_fact(value: object) -> dict[str, object]:
    return {
        "value": value,
        "confirmation_status": "confirmed",
        "source_type": "manual",
        "source_range": None,
    }


def _fixture() -> tuple[
    DecisionCase,
    DecisionReport,
    CandidateProfile,
    ResumeVersion,
    JobPosting,
    JobRequirementSnapshot,
]:
    owner_id = uuid4()
    posting = JobPosting.create(
        owner_id=owner_id,
        jd_text="负责构建智能检索服务，需要 Python 与向量检索经验。",
        job_title="AI 应用工程师",
        company_name="示例公司",
        location="上海",
    )
    profile = CandidateProfile.create(
        owner_id=owner_id,
        content={
            "basic_information": {"display_name": _profile_fact("候选人")},
            "preferences": {"target_locations": _profile_fact(["上海"])},
            "education": [],
            "experiences": [
                {
                    "id": "experience-1",
                    "job_title": _profile_fact("后端工程师"),
                    "responsibilities": _profile_fact(["构建搜索 API"]),
                }
            ],
            "skills": [{"id": "skill-1", "name": _profile_fact("Python")}],
        },
    )
    resume = ResumeVersion.publish(profile=profile, title="AI 求职简历", version=1)
    requirements = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        content={
            "required_skills": _requirement_fact(["Python", "向量检索"]),
            "minimum_experience_years": _requirement_fact(1),
            "degree_requirement": _requirement_fact("本科"),
            "location_requirement": _requirement_fact("上海"),
            "work_mode": _requirement_fact("hybrid"),
        },
    )
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        job_requirement_snapshot_id=requirements.id,
        job_requirement_snapshot_version=requirements.version,
        candidate_profile_id=profile.id,
        candidate_profile_version=profile.version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        rule_set_version=RULE_SET_VERSION,
    )
    result = RuleResult(
        rule_id="skills.coverage",
        rule_version="1",
        status=RuleStatus.PARTIAL,
        input_references=(
            RuleInputReference(
                source=RuleInputSource.CANDIDATE_PROFILE,
                object_id=profile.id,
                version=profile.version,
                field_path="skills[*].name",
            ),
        ),
        reason="已匹配 Python，向量检索经验需要进一步判断。",
    )
    report = DecisionReport.generate(
        decision_case=decision_case,
        evaluation=RuleSetEvaluation(
            decision_case_id=decision_case.id,
            rule_set_version=RULE_SET_VERSION,
            results=(result,),
        ),
        version=1,
        generator_version="m3-report-v1",
    )
    return decision_case, report, profile, resume, posting, requirements


def _model_output(profile_id: UUID) -> dict[str, Any]:
    transferable = {
        "text": "构建搜索 API 的经验可迁移到向量检索服务的接口与可靠性建设。",
        "citation_ids": ["profile-experience"],
    }
    return {
        "overall_fit": "moderate",
        "overall_fit_reason": {
            "text": "Python 能力匹配，但向量检索证据仍需补强。",
            "citation_ids": ["profile-skill", "job-skills"],
        },
        "strong_matches": [{"text": "已确认 Python 技能。", "citation_ids": ["profile-skill"]}],
        "transferable_evidence": [transferable],
        "critical_gaps": [],
        "non_blocking_gaps": [
            {"text": "缺少直接向量检索项目证据。", "citation_ids": ["job-skills"]}
        ],
        "resume_actions": [
            {"text": "补充搜索 API 的性能与可靠性结果。", "citation_ids": ["profile-experience"]}
        ],
        "project_deep_dive_risks": [],
        "interview_focus": [
            {"text": "准备说明传统搜索经验如何迁移。", "citation_ids": ["profile-experience"]}
        ],
        "unknowns": [],
        "citations": [
            {
                "citation_id": "profile-skill",
                "source": "candidate_profile",
                "object_id": str(profile_id),
                "version": 1,
                "field_path": "skills",
            },
            {
                "citation_id": "profile-experience",
                "source": "candidate_profile",
                "object_id": str(profile_id),
                "version": 1,
                "field_path": "experiences",
            },
        ],
    }


class _Repository:
    def __init__(self) -> None:
        self.items: list[JobFitAnalysis] = []
        self.commits = 0

    async def next_version(self, report_id: UUID) -> int:
        return 1 + max(
            (item.version for item in self.items if item.report_id == report_id), default=0
        )

    async def add(self, analysis: JobFitAnalysis) -> JobFitAnalysis:
        self.items.append(analysis)
        return analysis

    async def get_by_generation(self, identity: str) -> JobFitAnalysis | None:
        return next((item for item in self.items if item.generation_identity == identity), None)

    async def get_for_report(self, report_id: UUID) -> JobFitAnalysis | None:
        return next((item for item in reversed(self.items) if item.report_id == report_id), None)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_job_fit_publishes_cited_transferable_evidence_and_replays() -> None:
    case, report, profile, resume, posting, requirements = _fixture()
    output = _model_output(profile.id)
    output["citations"].append(
        {
            "citation_id": "job-skills",
            "source": "job_requirement_snapshot",
            "object_id": str(requirements.id),
            "version": requirements.version,
            "field_path": "required_skills",
        }
    )
    model = FakeModelAdapter([output])
    repository = _Repository()
    use_case = GenerateJobFitAnalysisUseCase(repository, model)
    command = GenerateJobFitAnalysisCommand(owner_id=case.owner_id)

    first = await use_case.execute(
        command,
        decision_case=case,
        report=report,
        profile=profile,
        resume=resume,
        posting=posting,
        requirements=requirements,
    )
    replay = await use_case.execute(
        command,
        decision_case=case,
        report=report,
        profile=profile,
        resume=resume,
        posting=posting,
        requirements=requirements,
    )

    assert first.analysis.transferable_evidence[0].text.startswith("构建搜索 API")
    assert first.analysis.overall_fit.value == "moderate"
    assert first.replayed is False
    assert replay.analysis == first.analysis
    assert replay.replayed is True
    assert len(model.requests) == 1
    assert model.requests[0].prompt_version == "job-fit-v1"
    assert model.requests[0].max_input_tokens == 20_000
    assert repository.commits == 1


@pytest.mark.asyncio
async def test_job_fit_rejects_out_of_scope_citation_before_persistence() -> None:
    case, report, profile, resume, posting, requirements = _fixture()
    output = _model_output(profile.id)
    output["citations"] = [
        {
            "citation_id": "profile-skill",
            "source": "candidate_profile",
            "object_id": str(uuid4()),
            "version": 1,
            "field_path": "skills",
        },
        {
            "citation_id": "profile-experience",
            "source": "candidate_profile",
            "object_id": str(profile.id),
            "version": 1,
            "field_path": "experiences",
        },
        {
            "citation_id": "job-skills",
            "source": "job_requirement_snapshot",
            "object_id": str(requirements.id),
            "version": 1,
            "field_path": "required_skills",
        },
    ]
    repository = _Repository()

    with pytest.raises(DomainError) as error:
        await GenerateJobFitAnalysisUseCase(repository, FakeModelAdapter([output])).execute(
            GenerateJobFitAnalysisCommand(owner_id=case.owner_id),
            decision_case=case,
            report=report,
            profile=profile,
            resume=resume,
            posting=posting,
            requirements=requirements,
        )

    assert error.value.error_code is ErrorCode.MODEL_OUTPUT_INVALID
    assert repository.items == []
    assert repository.commits == 0


@pytest.mark.asyncio
async def test_provider_failure_preserves_deterministic_report_and_writes_nothing() -> None:
    case, report, profile, resume, posting, requirements = _fixture()
    report_before = deepcopy(report.content)
    repository = _Repository()

    with pytest.raises(ModelError) as error:
        await GenerateJobFitAnalysisUseCase(repository, FakeModelAdapter([])).execute(
            GenerateJobFitAnalysisCommand(owner_id=case.owner_id),
            decision_case=case,
            report=report,
            profile=profile,
            resume=resume,
            posting=posting,
            requirements=requirements,
        )

    assert error.value.error_code is ErrorCode.MODEL_PROVIDER_FAILED
    assert report.content == report_before
    assert repository.items == []
    assert repository.commits == 0


@pytest.mark.asyncio
async def test_job_fit_rejects_mismatched_resume_version_and_company_owner() -> None:
    case, report, profile, resume, posting, requirements = _fixture()
    use_case = GenerateJobFitAnalysisUseCase(_Repository(), FakeModelAdapter([]))
    command = GenerateJobFitAnalysisCommand(owner_id=case.owner_id)

    with pytest.raises(ApplicationError) as resume_error:
        await use_case.execute(
            command,
            decision_case=case,
            report=report,
            profile=profile,
            resume=replace(resume, version=resume.version + 1),
            posting=posting,
            requirements=requirements,
        )
    assert resume_error.value.error_code is ErrorCode.DECISION_INPUT_CONFLICT

    foreign_company = cast(
        CompanySnapshot,
        SimpleNamespace(owner_id=uuid4()),
    )
    with pytest.raises(ApplicationError) as owner_error:
        await use_case.execute(
            command,
            decision_case=case,
            report=report,
            profile=profile,
            resume=resume,
            posting=posting,
            requirements=requirements,
            company_snapshot=foreign_company,
        )
    assert owner_error.value.error_code is ErrorCode.ENTITY_NOT_FOUND


@pytest.mark.asyncio
async def test_job_fit_bounds_large_fixed_evidence_before_model_request() -> None:
    case, report, profile, resume, posting, requirements = _fixture()
    output = _model_output(profile.id)
    output["citations"].append(
        {
            "citation_id": "job-skills",
            "source": "job_requirement_snapshot",
            "object_id": str(requirements.id),
            "version": requirements.version,
            "field_path": "required_skills",
        }
    )
    model = FakeModelAdapter([output])

    await GenerateJobFitAnalysisUseCase(_Repository(), model).execute(
        GenerateJobFitAnalysisCommand(owner_id=case.owner_id),
        decision_case=case,
        report=report,
        profile=profile,
        resume=resume,
        posting=replace(posting, jd_text="x" * 100_000),
        requirements=requirements,
    )

    request = model.requests[0]
    assert len(request.system_prompt) + len(request.user_input) <= MAX_MODEL_PROMPT_CHARS
    catalog = json.loads(request.user_input)["evidence_catalog"]
    jd_evidence = next(item for item in catalog if item["field_path"] == "jd_text")
    assert jd_evidence["value"]["truncated"] is True
    assert jd_evidence["value"]["original_chars"] == 100_002
