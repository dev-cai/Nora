"""Versioned deterministic DecisionReport domain and application tests."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.decision import (
    GenerateDecisionReportCommand,
    GenerateDecisionReportUseCase,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import CandidateProfile
from app.domain.decision import (
    RULE_SET_VERSION,
    DecisionCase,
    DecisionReport,
    ReportSection,
    RuleInputReference,
    RuleInputSource,
    RuleResult,
    RuleSetEvaluation,
    RuleStatus,
)
from app.domain.opportunity import JobRequirementSnapshot


def _reference(source: RuleInputSource, object_id: UUID, field_path: str) -> RuleInputReference:
    return RuleInputReference(
        source=source,
        object_id=object_id,
        version=1,
        field_path=field_path,
    )


def _domain_fixture() -> tuple[DecisionCase, RuleSetEvaluation]:
    owner_id = uuid4()
    posting_id = uuid4()
    requirement_id = uuid4()
    profile_id = uuid4()
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=posting_id,
        job_posting_version=1,
        job_requirement_snapshot_id=requirement_id,
        job_requirement_snapshot_version=1,
        candidate_profile_id=profile_id,
        candidate_profile_version=1,
        resume_version_id=uuid4(),
        resume_version=1,
        rule_set_version=RULE_SET_VERSION,
    )
    requirement_ref = _reference(
        RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
        requirement_id,
        "required_skills",
    )
    profile_ref = _reference(RuleInputSource.CANDIDATE_PROFILE, profile_id, "skills[*].name")
    results = (
        RuleResult(
            rule_id="skills.coverage",
            rule_version="1",
            status=RuleStatus.MATCH,
            input_references=(requirement_ref, profile_ref),
            reason="技能要求全部满足。",
        ),
        RuleResult(
            rule_id="experience.minimum_years",
            rule_version="1",
            status=RuleStatus.PARTIAL,
            input_references=(
                _reference(
                    RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
                    requirement_id,
                    "minimum_experience_years",
                ),
            ),
            reason="经验接近要求。",
            suggestion="确认可折算的项目经验。",
        ),
        RuleResult(
            rule_id="degree.minimum",
            rule_version="1",
            status=RuleStatus.UNKNOWN,
            input_references=(
                _reference(
                    RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
                    requirement_id,
                    "degree_requirement",
                ),
            ),
            reason="学历要求尚未确认。",
            uncertainty="缺少 confirmed 的学历要求。",
        ),
        RuleResult(
            rule_id="location_work_mode.compatibility",
            rule_version="1",
            status=RuleStatus.MISMATCH,
            input_references=(
                _reference(
                    RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
                    requirement_id,
                    "location_requirement",
                ),
            ),
            reason="地点要求不匹配。",
            suggestion="确认是否接受异地机会。",
        ),
    )
    return decision_case, RuleSetEvaluation(
        decision_case_id=decision_case.id,
        rule_set_version=RULE_SET_VERSION,
        results=results,
    )


def test_report_contains_five_sections_summary_and_traceability() -> None:
    decision_case, evaluation = _domain_fixture()
    generated_at = datetime(2026, 8, 12, tzinfo=timezone.utc)

    report = DecisionReport.generate(
        decision_case=decision_case,
        evaluation=evaluation,
        version=1,
        generator_version=" generator-v1 ",
        now=generated_at,
    )

    assert report.owner_id == decision_case.owner_id
    assert report.decision_case_id == decision_case.id
    assert report.rule_set_version == RULE_SET_VERSION
    assert report.generator_version == "generator-v1"
    assert report.generated_at == generated_at
    assert report.summary.match == 1
    assert report.summary.partial == 1
    assert report.summary.mismatch == 1
    assert report.summary.unknown == 1
    assert set(report.content) >= {section.value for section in ReportSection}
    assert report.satisfied_conditions == ("技能要求全部满足。",)
    assert report.gaps == ("经验接近要求。", "地点要求不匹配。")
    assert report.risks == ("缺少 confirmed 的学历要求。", "地点要求不匹配。")
    assert report.next_steps == (
        "确认可折算的项目经验。",
        "补充或确认缺失输入后重新生成报告。",
        "确认是否接受异地机会。",
    )
    assert len(report.unknowns) == 1
    assert {item.source_rule_id for item in report.recommendations} == {
        "experience.minimum_years",
        "degree.minimum",
        "location_work_mode.compatibility",
    }
    fact_citations = {citation for fact in report.facts for citation in fact.citation_ids}
    partial_citation = report.rule_results[1].citation_ids[0]
    unknown_citation = report.rule_results[2].citation_ids[0]
    assert partial_citation not in fact_citations
    assert unknown_citation not in fact_citations


def test_report_content_is_a_safe_copy_and_round_trips() -> None:
    decision_case, evaluation = _domain_fixture()
    report = DecisionReport.generate(
        decision_case=decision_case,
        evaluation=evaluation,
        version=2,
        generator_version="generator-v2",
    )
    content = report.content
    original = deepcopy(content)
    content[ReportSection.FACT.value].clear()
    assert report.content == original

    restored = DecisionReport.restore(
        report_id=report.id,
        owner_id=report.owner_id,
        decision_case_id=report.decision_case_id,
        version=report.version,
        rule_set_version=report.rule_set_version,
        generator_version=report.generator_version,
        content=report.content,
        generated_at=report.generated_at,
    )
    assert restored == report


def test_report_rejects_mismatched_case_and_rule_set() -> None:
    decision_case, evaluation = _domain_fixture()
    with pytest.raises(DomainError, match="does not belong") as case_error:
        DecisionReport.generate(
            decision_case=decision_case,
            evaluation=replace(evaluation, decision_case_id=uuid4()),
            version=1,
            generator_version="generator-v1",
        )
    assert case_error.value.error_code == "report_input_mismatch"

    with pytest.raises(DomainError, match="different rule set") as rules_error:
        DecisionReport.generate(
            decision_case=decision_case,
            evaluation=replace(evaluation, rule_set_version="rules-v2"),
            version=1,
            generator_version="generator-v1",
        )
    assert rules_error.value.error_code == "report_input_mismatch"


def _fact(value: object, status: str = "confirmed") -> dict[str, object]:
    return {"value": value, "confirmation_status": status}


def _application_fixture() -> tuple[DecisionCase, CandidateProfile, JobRequirementSnapshot]:
    owner_id = uuid4()
    posting_id = uuid4()
    profile = CandidateProfile.create(
        owner_id=owner_id,
        content={
            "preferences": {
                "target_locations": _fact(["上海"]),
                "accepts_remote": _fact(True),
            },
            "education": [],
            "experiences": [],
            "skills": [{"id": "skill-1", "name": _fact("Python")}],
        },
    )
    confirmed = {
        "confirmation_status": "confirmed",
        "source_type": "manual",
        "source_range": None,
    }
    requirements = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting_id,
        job_posting_version=1,
        content={
            "required_skills": {**confirmed, "value": ["Python"]},
            "minimum_experience_years": {**confirmed, "value": 1},
            "degree_requirement": {**confirmed, "value": "本科"},
            "location_requirement": {**confirmed, "value": "上海"},
            "work_mode": {**confirmed, "value": "remote"},
        },
    )
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=posting_id,
        job_posting_version=1,
        job_requirement_snapshot_id=requirements.id,
        job_requirement_snapshot_version=1,
        candidate_profile_id=profile.id,
        candidate_profile_version=1,
        resume_version_id=uuid4(),
        resume_version=1,
        rule_set_version=RULE_SET_VERSION,
    )
    return decision_case, profile, requirements


class _ReportRepository:
    def __init__(self) -> None:
        self.reports: list[DecisionReport] = []

    async def next_version(self, decision_case_id: UUID) -> int:
        return len([item for item in self.reports if item.decision_case_id == decision_case_id]) + 1

    async def add(self, report: DecisionReport) -> DecisionReport:
        self.reports.append(report)
        return report

    async def get_by_generation(
        self, decision_case_id: UUID, rule_set_version: str, generator_version: str
    ) -> DecisionReport | None:
        return next(
            (
                item
                for item in self.reports
                if item.decision_case_id == decision_case_id
                and item.rule_set_version == rule_set_version
                and item.generator_version == generator_version
            ),
            None,
        )

    async def get_by_id(self, report_id: UUID) -> DecisionReport | None:
        return next((item for item in self.reports if item.id == report_id), None)

    async def list_for_case(self, decision_case_id: UUID) -> list[DecisionReport]:
        return [item for item in self.reports if item.decision_case_id == decision_case_id]

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_generate_use_case_replays_and_versions_generator_upgrades() -> None:
    decision_case, profile, requirements = _application_fixture()
    repository = _ReportRepository()
    use_case = GenerateDecisionReportUseCase(repository)

    first = await use_case.execute(
        GenerateDecisionReportCommand(decision_case.owner_id, "generator-v1"),
        decision_case=decision_case,
        candidate_profile=profile,
        requirements=requirements,
    )
    replay = await use_case.execute(
        GenerateDecisionReportCommand(decision_case.owner_id, "  generator-v1 "),
        decision_case=decision_case,
        candidate_profile=profile,
        requirements=requirements,
    )
    upgraded = await use_case.execute(
        GenerateDecisionReportCommand(decision_case.owner_id, "generator-v2"),
        decision_case=decision_case,
        candidate_profile=profile,
        requirements=requirements,
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.report.id == first.report.id
    assert upgraded.replayed is False
    assert upgraded.report.version == 2
    assert [item.generator_version for item in repository.reports] == [
        "generator-v1",
        "generator-v2",
    ]


@pytest.mark.asyncio
async def test_generate_use_case_hides_cross_owner_case() -> None:
    decision_case, profile, requirements = _application_fixture()
    with pytest.raises(ApplicationError) as error:
        await GenerateDecisionReportUseCase(_ReportRepository()).execute(
            GenerateDecisionReportCommand(uuid4(), "generator-v1"),
            decision_case=decision_case,
            candidate_profile=profile,
            requirements=requirements,
        )
    assert error.value.error_code == "entity_not_found"
