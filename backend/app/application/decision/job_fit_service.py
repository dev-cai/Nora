"""Generate an immutable AI job-fit analysis from fixed DecisionReport inputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from app.application.model import (
    JOB_FIT_PROMPT_VERSION,
    StructuredJobFitAnalysis,
)
from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.career import CandidateProfile, ResumeVersion
from app.domain.decision import (
    DecisionCase,
    DecisionReport,
    JobFitAnalysis,
    JobFitCitation,
    JobFitCitationSource,
    JobFitInsight,
    JobFitLevel,
)
from app.domain.opportunity import CompanySnapshot, JobPosting, JobRequirementSnapshot
from app.ports.decision import JobFitAnalysisRepository
from app.ports.model import ModelPort, ModelRequest

JOB_FIT_PROVIDER = "dashscope-cn-beijing"
JOB_FIT_MODEL = "qwen3.8-max"
JOB_FIT_GENERATOR_VERSION = "job-fit-analysis-v1"
MAX_EVIDENCE_PREVIEW_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class GenerateJobFitAnalysisCommand:
    owner_id: UUID
    generator_version: str = JOB_FIT_GENERATOR_VERSION


@dataclass(frozen=True, slots=True)
class GenerateJobFitAnalysisResult:
    analysis: JobFitAnalysis
    replayed: bool


class GenerateJobFitAnalysisUseCase:
    """Call the model only with fixed, user-owned evidence and publish validated output."""

    def __init__(self, repository: JobFitAnalysisRepository, model: ModelPort) -> None:
        self.repository = repository
        self.model = model

    async def execute(
        self,
        command: GenerateJobFitAnalysisCommand,
        *,
        decision_case: DecisionCase,
        report: DecisionReport,
        profile: CandidateProfile,
        resume: ResumeVersion,
        posting: JobPosting,
        requirements: JobRequirementSnapshot,
        company_snapshot: CompanySnapshot | None = None,
    ) -> GenerateJobFitAnalysisResult:
        self._validate_inputs(
            command.owner_id,
            decision_case,
            report,
            profile,
            resume,
            posting,
            requirements,
            company_snapshot,
        )
        fixed_inputs = _fixed_inputs(
            decision_case,
            report,
            profile,
            resume,
            posting,
            requirements,
            company_snapshot,
        )
        generation_identity = JobFitAnalysis.generation_key(
            owner_id=command.owner_id,
            report_id=report.id,
            report_version=report.version,
            decision_case_id=decision_case.id,
            fixed_inputs=fixed_inputs,
            prompt_version=JOB_FIT_PROMPT_VERSION,
            provider=JOB_FIT_PROVIDER,
            model=JOB_FIT_MODEL,
            generator_version=command.generator_version,
        )
        existing = await self.repository.get_by_generation(generation_identity)
        if existing is not None:
            return GenerateJobFitAnalysisResult(existing, True)

        evidence, allowed_citations = _evidence_catalog(
            profile=profile,
            resume=resume,
            posting=posting,
            requirements=requirements,
            report=report,
            company_snapshot=company_snapshot,
        )
        request = ModelRequest(
            system_prompt=(
                "You are Nora's job-fit analysis assistant. Return only the JSON schema. "
                "Infer transferable skills, relevance, gaps and interview focus from the fixed "
                "evidence catalog. Every item, including overall_fit_reason and unknowns, must "
                "cite one or more catalog entries. Never invent facts, never cite outside the "
                "catalog, and never claim an inference is a confirmed fact."
            ),
            user_input=json.dumps(
                {
                    "fixed_inputs": [
                        {"source": source, "object_id": str(object_id), "version": version}
                        for source, object_id, version in fixed_inputs
                    ],
                    "evidence_catalog": evidence,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            prompt_version=JOB_FIT_PROMPT_VERSION,
            max_input_tokens=20_000,
            max_output_tokens=4_000,
            temperature=0.2,
        )
        output = await self.model.generate_structured(request, StructuredJobFitAnalysis)
        analysis = JobFitAnalysis.publish(
            owner_id=command.owner_id,
            report_id=report.id,
            report_version=report.version,
            decision_case_id=decision_case.id,
            version=await self.repository.next_version(report.id),
            prompt_version=JOB_FIT_PROMPT_VERSION,
            provider=JOB_FIT_PROVIDER,
            model=JOB_FIT_MODEL,
            generator_version=command.generator_version,
            generation_identity=generation_identity,
            overall_fit=JobFitLevel(output.overall_fit),
            overall_fit_reason=_insight(output.overall_fit_reason),
            strong_matches=tuple(_insight(item) for item in output.strong_matches),
            transferable_evidence=tuple(_insight(item) for item in output.transferable_evidence),
            critical_gaps=tuple(_insight(item) for item in output.critical_gaps),
            non_blocking_gaps=tuple(_insight(item) for item in output.non_blocking_gaps),
            resume_actions=tuple(_insight(item) for item in output.resume_actions),
            project_deep_dive_risks=tuple(
                _insight(item) for item in output.project_deep_dive_risks
            ),
            interview_focus=tuple(_insight(item) for item in output.interview_focus),
            unknowns=tuple(_insight(item) for item in output.unknowns),
            citations=tuple(
                JobFitCitation(
                    citation_id=item.citation_id,
                    source=JobFitCitationSource(item.source),
                    object_id=item.object_id,
                    version=item.version,
                    field_path=item.field_path,
                )
                for item in output.citations
            ),
            allowed_citations=allowed_citations,
        )
        try:
            stored = await self.repository.add(analysis)
            await self.repository.commit()
        except InfrastructureError as exc:
            if exc.error_code is not ErrorCode.DECISION_REPORT_GENERATION_CONFLICT:
                raise
            replay = await self.repository.get_by_generation(generation_identity)
            if replay is None:
                raise
            return GenerateJobFitAnalysisResult(replay, True)
        return GenerateJobFitAnalysisResult(stored, False)

    @staticmethod
    def _validate_inputs(
        owner_id: UUID,
        decision_case: DecisionCase,
        report: DecisionReport,
        profile: CandidateProfile,
        resume: ResumeVersion,
        posting: JobPosting,
        requirements: JobRequirementSnapshot,
        company_snapshot: CompanySnapshot | None,
    ) -> None:
        inputs = (decision_case, report, profile, resume, posting, requirements)
        if any(item.owner_id != owner_id for item in inputs):
            raise ApplicationError("Job-fit input not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        if (
            report.decision_case_id != decision_case.id
            or resume.id != decision_case.resume_version_id
            or resume.version != decision_case.resume_version
        ):
            raise ApplicationError(
                "Job-fit input versions do not match",
                error_code=ErrorCode.DECISION_INPUT_CONFLICT,
            )
        if company_snapshot is not None and company_snapshot.owner_id != owner_id:
            raise ApplicationError("Job-fit input not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        if (
            profile.id != decision_case.candidate_profile_id
            or profile.version != decision_case.candidate_profile_version
            or posting.id != decision_case.job_posting_id
            or posting.version != decision_case.job_posting_version
            or requirements.id != decision_case.job_requirement_snapshot_id
            or requirements.version != decision_case.job_requirement_snapshot_version
        ):
            raise ApplicationError(
                "Job-fit input versions do not match",
                error_code=ErrorCode.DECISION_INPUT_CONFLICT,
            )


def _insight(value: Any) -> JobFitInsight:
    return JobFitInsight(text=value.text, citation_ids=tuple(value.citation_ids))


def _fixed_inputs(
    case: DecisionCase,
    report: DecisionReport,
    profile: CandidateProfile,
    resume: ResumeVersion,
    posting: JobPosting,
    requirements: JobRequirementSnapshot,
    company_snapshot: CompanySnapshot | None,
) -> tuple[tuple[str, UUID, int], ...]:
    values = [
        (JobFitCitationSource.CANDIDATE_PROFILE.value, profile.id, profile.version),
        (JobFitCitationSource.RESUME_VERSION.value, resume.id, resume.version),
        (JobFitCitationSource.JOB_POSTING.value, posting.id, posting.version),
        (
            JobFitCitationSource.JOB_REQUIREMENT_SNAPSHOT.value,
            requirements.id,
            requirements.version,
        ),
        (JobFitCitationSource.DECISION_REPORT.value, report.id, report.version),
    ]
    if company_snapshot is not None:
        values.append(
            (
                JobFitCitationSource.COMPANY_SNAPSHOT.value,
                company_snapshot.id,
                company_snapshot.version,
            )
        )
    return tuple(values)


def _evidence_catalog(
    *,
    profile: CandidateProfile,
    resume: ResumeVersion,
    posting: JobPosting,
    requirements: JobRequirementSnapshot,
    report: DecisionReport,
    company_snapshot: CompanySnapshot | None,
) -> tuple[list[dict[str, Any]], frozenset[tuple[str, UUID, int, str]]]:
    catalog: list[dict[str, Any]] = []
    allowed: set[tuple[str, UUID, int, str]] = set()

    def add(
        source: JobFitCitationSource,
        object_id: UUID,
        version: int,
        field_path: str,
        value: Any,
    ) -> None:
        allowed.add((source.value, object_id, version, field_path))
        catalog.append(
            {
                "citation_id": f"{source.value}:{object_id}:{version}:{field_path}",
                "source": source.value,
                "object_id": str(object_id),
                "version": version,
                "field_path": field_path,
                "value": _bounded_evidence(value),
            }
        )

    confirmed_profile = profile.confirmed_data()
    for field in (
        "basic_information",
        "preferences",
        "experiences",
        "skills",
        "education",
    ):
        add(
            JobFitCitationSource.CANDIDATE_PROFILE,
            profile.id,
            profile.version,
            field,
            confirmed_profile.get(field, {}),
        )
    add(
        JobFitCitationSource.RESUME_VERSION,
        resume.id,
        resume.version,
        "content",
        resume.content,
    )
    for field in ("jd_text", "job_title", "company_name", "location"):
        add(
            JobFitCitationSource.JOB_POSTING,
            posting.id,
            posting.version,
            field,
            getattr(posting, field),
        )
    requirements_data = requirements.confirmed_requirements()
    for field in (
        "required_skills",
        "minimum_experience_years",
        "degree_requirement",
        "location_requirement",
        "work_mode",
    ):
        add(
            JobFitCitationSource.JOB_REQUIREMENT_SNAPSHOT,
            requirements.id,
            requirements.version,
            field,
            requirements_data.get(field),
        )
    report_content = report.content
    for field in ("summary", "rule_results", "gaps", "risks"):
        add(
            JobFitCitationSource.DECISION_REPORT,
            report.id,
            report.version,
            field,
            report_content.get(field, []),
        )
    if company_snapshot is not None:
        for field in ("company_name", "size", "industry", "review_summary"):
            add(
                JobFitCitationSource.COMPANY_SNAPSHOT,
                company_snapshot.id,
                company_snapshot.version,
                field,
                getattr(company_snapshot, field),
            )
    return catalog, frozenset(allowed)


def _bounded_evidence(value: Any) -> Any:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(serialized) <= MAX_EVIDENCE_PREVIEW_CHARS:
        return value
    return {
        "preview": serialized[:MAX_EVIDENCE_PREVIEW_CHARS],
        "truncated": True,
        "original_chars": len(serialized),
        "sha256": sha256(serialized.encode()).hexdigest(),
    }
