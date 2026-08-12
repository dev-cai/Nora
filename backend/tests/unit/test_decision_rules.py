"""Deterministic DecisionCase rule engine tests."""

from copy import deepcopy
from uuid import uuid4

import pytest
from app.domain.base.exceptions import DomainError
from app.domain.career import CandidateProfile
from app.domain.decision import (
    RULE_SET_VERSION,
    DecisionCase,
    RuleInputSource,
    RuleStatus,
    evaluate_decision_rules,
)
from app.domain.opportunity import JobRequirementSnapshot


def _fact(value, status: str = "confirmed") -> dict[str, object]:
    return {"value": value, "confirmation_status": status}


def _profile_content() -> dict[str, object]:
    return {
        "basic_information": {
            "display_name": _fact("Alice"),
            "current_location": _fact("上海"),
        },
        "preferences": {
            "target_locations": _fact(["上海", "杭州"]),
            "accepts_remote": _fact(True),
            "target_roles": _fact(["后端工程师"]),
        },
        "education": [
            {
                "id": "education-1",
                "school": _fact("Example University"),
                "degree": _fact("本科"),
                "major": _fact("Computer Science"),
                "start_date": _fact("2017-09-01"),
                "end_date": _fact("2021-06-30"),
            }
        ],
        "experiences": [
            {
                "id": "experience-1",
                "company": _fact("Example Corp"),
                "job_title": _fact("Backend Engineer"),
                "start_date": _fact("2021-07-01"),
                "end_date": _fact("2024-07-01"),
                "responsibilities": _fact(["Build APIs"]),
                "achievements": _fact([]),
            }
        ],
        "skills": [
            {
                "id": "skill-1",
                "name": _fact("Python"),
                "proficiency": _fact("advanced"),
                "years": _fact(3),
            },
            {
                "id": "skill-2",
                "name": _fact("SQL"),
                "proficiency": _fact("intermediate"),
                "years": _fact(2),
            },
        ],
    }


def _requirement_content() -> dict[str, object]:
    confirmed = {
        "confirmation_status": "confirmed",
        "source_type": "manual",
        "source_range": None,
    }
    return {
        "required_skills": {**confirmed, "value": ["python", "Go"]},
        "minimum_experience_years": {**confirmed, "value": 3},
        "degree_requirement": {**confirmed, "value": "本科"},
        "location_requirement": {**confirmed, "value": "上海"},
        "work_mode": {**confirmed, "value": "hybrid"},
    }


def _fixture(
    *,
    profile_content: dict[str, object] | None = None,
    requirement_content: dict[str, object] | None = None,
) -> tuple[DecisionCase, CandidateProfile, JobRequirementSnapshot]:
    owner_id = uuid4()
    posting_id = uuid4()
    profile = CandidateProfile.create(
        owner_id=owner_id,
        content=profile_content or _profile_content(),
    )
    requirements = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting_id,
        job_posting_version=1,
        content=requirement_content or _requirement_content(),
    )
    decision_case = DecisionCase.create(
        owner_id=owner_id,
        job_posting_id=posting_id,
        job_posting_version=1,
        job_requirement_snapshot_id=requirements.id,
        job_requirement_snapshot_version=requirements.version,
        candidate_profile_id=profile.id,
        candidate_profile_version=profile.version,
        resume_version_id=uuid4(),
        resume_version=1,
        rule_set_version=RULE_SET_VERSION,
    )
    return decision_case, profile, requirements


def _results_by_id(case, profile, requirements):
    evaluation = evaluate_decision_rules(case, profile, requirements)
    return evaluation, {result.rule_id: result for result in evaluation.results}


def test_rule_set_is_repeatable_ordered_and_traceable() -> None:
    decision_case, profile, requirements = _fixture()

    first = evaluate_decision_rules(decision_case, profile, requirements)
    second = evaluate_decision_rules(decision_case, profile, requirements)

    assert first == second
    assert first.rule_set_version == RULE_SET_VERSION
    assert [result.rule_id for result in first.results] == [
        "skills.coverage",
        "experience.minimum_years",
        "location_work_mode.compatibility",
        "degree.minimum",
    ]
    for result in first.results:
        assert result.rule_version == "1"
        assert all(reference.version == 1 for reference in result.input_references)
        assert {reference.source for reference in result.input_references} <= {
            RuleInputSource.CANDIDATE_PROFILE,
            RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
        }


def test_skill_rule_reports_partial_and_missing_skills() -> None:
    decision_case, profile, requirements = _fixture()
    _, results = _results_by_id(decision_case, profile, requirements)

    skill = results["skills.coverage"]
    assert skill.status is RuleStatus.PARTIAL
    assert "1/2" in skill.reason
    assert skill.suggestion is not None and "go" in skill.suggestion


def test_skill_rule_matches_case_insensitively_and_rejects_no_coverage() -> None:
    requirements_content = _requirement_content()
    requirements_content["required_skills"]["value"] = [" PYTHON ", "sql"]
    decision_case, profile, requirements = _fixture(requirement_content=requirements_content)
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["skills.coverage"].status is RuleStatus.MATCH

    profile_content = _profile_content()
    profile_content["skills"] = [{"id": "skill-1", "name": _fact("Java"), "years": _fact(3)}]
    decision_case, profile, requirements = _fixture(profile_content=profile_content)
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["skills.coverage"].status is RuleStatus.MISMATCH


def test_experience_rule_matches_boundary_and_merges_overlaps() -> None:
    profile_content = _profile_content()
    profile_content["experiences"] = [
        {
            "id": "experience-1",
            "start_date": _fact("2020-01-01"),
            "end_date": _fact("2022-01-01"),
        },
        {
            "id": "experience-2",
            "start_date": _fact("2021-01-01"),
            "end_date": _fact("2023-01-01"),
        },
    ]
    decision_case, profile, requirements = _fixture(profile_content=profile_content)
    _, results = _results_by_id(decision_case, profile, requirements)

    assert results["experience.minimum_years"].status is RuleStatus.MATCH


def test_experience_rule_is_unknown_when_incomplete_dates_can_change_result() -> None:
    profile_content = _profile_content()
    profile_content["experiences"] = [
        {
            "id": "experience-1",
            "start_date": _fact("2023-01-01"),
            "end_date": _fact("2024-01-01"),
        },
        {
            "id": "experience-2",
            "start_date": _fact("2024-01-02"),
            "end_date": _fact(None),
        },
    ]
    decision_case, profile, requirements = _fixture(profile_content=profile_content)
    _, results = _results_by_id(decision_case, profile, requirements)

    result = results["experience.minimum_years"]
    assert result.status is RuleStatus.UNKNOWN
    assert result.uncertainty is not None


def test_experience_rule_mismatches_complete_short_history() -> None:
    profile_content = _profile_content()
    profile_content["experiences"][0]["start_date"] = _fact("2023-01-01")
    profile_content["experiences"][0]["end_date"] = _fact("2024-01-01")
    decision_case, profile, requirements = _fixture(profile_content=profile_content)
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["experience.minimum_years"].status is RuleStatus.MISMATCH


@pytest.mark.parametrize(
    ("work_mode", "accepts_remote", "location", "expected"),
    [
        ("remote", True, "上海", RuleStatus.MATCH),
        ("remote", True, "北京", RuleStatus.MATCH),
        ("remote", False, "上海", RuleStatus.MISMATCH),
        ("onsite", True, "北京", RuleStatus.MISMATCH),
    ],
)
def test_location_and_work_mode_rule(
    work_mode: str,
    accepts_remote: bool,
    location: str,
    expected: RuleStatus,
) -> None:
    profile_content = _profile_content()
    profile_content["preferences"]["accepts_remote"] = _fact(accepts_remote)
    requirements_content = _requirement_content()
    requirements_content["work_mode"]["value"] = work_mode
    requirements_content["location_requirement"]["value"] = location
    decision_case, profile, requirements = _fixture(
        profile_content=profile_content,
        requirement_content=requirements_content,
    )
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["location_work_mode.compatibility"].status is expected


def test_location_rule_is_partial_when_only_location_is_confirmed() -> None:
    requirements_content = _requirement_content()
    requirements_content["work_mode"] = {
        "value": None,
        "confirmation_status": "unknown",
        "source_type": "manual",
        "source_range": None,
    }
    decision_case, profile, requirements = _fixture(requirement_content=requirements_content)
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["location_work_mode.compatibility"].status is RuleStatus.PARTIAL


@pytest.mark.parametrize(
    ("candidate_degree", "required_degree", "expected"),
    [
        ("硕士", "本科", RuleStatus.MATCH),
        ("大专", "本科", RuleStatus.MISMATCH),
        ("BS", "本科", RuleStatus.MATCH),
        ("职业证书", "本科", RuleStatus.UNKNOWN),
    ],
)
def test_degree_rule_uses_explicit_degree_order(
    candidate_degree: str,
    required_degree: str,
    expected: RuleStatus,
) -> None:
    profile_content = _profile_content()
    profile_content["education"][0]["degree"] = _fact(candidate_degree)
    requirements_content = _requirement_content()
    requirements_content["degree_requirement"]["value"] = required_degree
    decision_case, profile, requirements = _fixture(
        profile_content=profile_content,
        requirement_content=requirements_content,
    )
    _, results = _results_by_id(decision_case, profile, requirements)
    assert results["degree.minimum"].status is expected


def test_unconfirmed_fields_produce_unknown_instead_of_guessing() -> None:
    profile_content = _profile_content()
    profile_content["skills"][0]["name"] = _fact("Python", "unconfirmed")
    profile_content["skills"][1]["name"] = _fact("SQL", "unconfirmed")
    requirements_content = _requirement_content()
    requirements_content["degree_requirement"] = {
        "value": None,
        "confirmation_status": "unknown",
        "source_type": "manual",
        "source_range": None,
    }
    decision_case, profile, requirements = _fixture(
        profile_content=profile_content,
        requirement_content=requirements_content,
    )
    _, results = _results_by_id(decision_case, profile, requirements)

    assert results["skills.coverage"].status is RuleStatus.UNKNOWN
    assert results["degree.minimum"].status is RuleStatus.UNKNOWN


def test_rule_engine_rejects_inputs_outside_decision_case() -> None:
    decision_case, profile, requirements = _fixture()
    other_profile = CandidateProfile.create(
        owner_id=profile.owner_id,
        content=deepcopy(_profile_content()),
    )

    with pytest.raises(DomainError) as error:
        evaluate_decision_rules(decision_case, other_profile, requirements)
    assert error.value.error_code == "decision_rule_input_mismatch"


def test_rule_engine_rejects_unsupported_rule_set_version() -> None:
    decision_case, profile, requirements = _fixture()
    unsupported = DecisionCase.create(
        owner_id=decision_case.owner_id,
        job_posting_id=decision_case.job_posting_id,
        job_posting_version=decision_case.job_posting_version,
        job_requirement_snapshot_id=decision_case.job_requirement_snapshot_id,
        job_requirement_snapshot_version=decision_case.job_requirement_snapshot_version,
        candidate_profile_id=decision_case.candidate_profile_id,
        candidate_profile_version=decision_case.candidate_profile_version,
        resume_version_id=decision_case.resume_version_id,
        resume_version=decision_case.resume_version,
        rule_set_version="future-rules-v2",
    )

    with pytest.raises(DomainError) as error:
        evaluate_decision_rules(unsupported, profile, requirements)
    assert error.value.error_code == "unsupported_rule_set_version"
