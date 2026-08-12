"""M3 deterministic rules over confirmed decision inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.base.exceptions import DomainError
from app.domain.career import CandidateProfile
from app.domain.opportunity import JobRequirementSnapshot

from .decision_case import DecisionCase

RULE_SET_VERSION = "m3-rules-v1"
RULE_VERSION = "1"


class RuleStatus(StrEnum):
    """Stable result states shared by all deterministic rules."""

    MATCH = "match"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class RuleInputSource(StrEnum):
    """Versioned business facts consumed by a rule."""

    CANDIDATE_PROFILE = "candidate_profile"
    JOB_REQUIREMENT_SNAPSHOT = "job_requirement_snapshot"


@dataclass(frozen=True, slots=True)
class RuleInputReference:
    """A field path inside one immutable input version."""

    source: RuleInputSource
    object_id: UUID
    version: int
    field_path: str


@dataclass(frozen=True, slots=True)
class RuleResult:
    """One explainable and traceable deterministic rule result."""

    rule_id: str
    rule_version: str
    status: RuleStatus
    input_references: tuple[RuleInputReference, ...]
    reason: str
    uncertainty: str | None = None
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class RuleSetEvaluation:
    """Ordered results produced by one immutable rule set version."""

    decision_case_id: UUID
    rule_set_version: str
    results: tuple[RuleResult, ...]


def evaluate_decision_rules(
    decision_case: DecisionCase,
    candidate_profile: CandidateProfile,
    requirements: JobRequirementSnapshot,
) -> RuleSetEvaluation:
    """Evaluate the M3 rule set without I/O, model calls, or free-text inference."""

    _validate_inputs(decision_case, candidate_profile, requirements)
    profile = candidate_profile.confirmed_data()
    confirmed_requirements = requirements.confirmed_requirements()
    results = (
        _evaluate_skills(candidate_profile, requirements, profile, confirmed_requirements),
        _evaluate_experience(candidate_profile, requirements, profile, confirmed_requirements),
        _evaluate_location_and_work_mode(
            candidate_profile, requirements, profile, confirmed_requirements
        ),
        _evaluate_degree(candidate_profile, requirements, profile, confirmed_requirements),
    )
    return RuleSetEvaluation(
        decision_case_id=decision_case.id,
        rule_set_version=RULE_SET_VERSION,
        results=results,
    )


def _validate_inputs(
    decision_case: DecisionCase,
    candidate_profile: CandidateProfile,
    requirements: JobRequirementSnapshot,
) -> None:
    if decision_case.rule_set_version != RULE_SET_VERSION:
        raise DomainError(
            "Decision case uses an unsupported rule set",
            error_code="unsupported_rule_set_version",
        )
    valid = (
        decision_case.owner_id == candidate_profile.owner_id == requirements.owner_id
        and decision_case.candidate_profile_id == candidate_profile.id
        and decision_case.candidate_profile_version == candidate_profile.version
        and decision_case.job_requirement_snapshot_id == requirements.id
        and decision_case.job_requirement_snapshot_version == requirements.version
        and decision_case.job_posting_id == requirements.job_posting_id
        and decision_case.job_posting_version == requirements.job_posting_version
    )
    if not valid:
        raise DomainError(
            "Rule inputs do not match the decision case",
            error_code="decision_rule_input_mismatch",
        )


def _evaluate_skills(
    profile_version: CandidateProfile,
    requirement_version: JobRequirementSnapshot,
    profile: dict[str, Any],
    requirements: dict[str, Any],
) -> RuleResult:
    references = (
        _requirement_ref(requirement_version, "required_skills"),
        _profile_ref(profile_version, "skills[*].name"),
    )
    required_value = requirements.get("required_skills")
    if not isinstance(required_value, list):
        return _unknown(
            "skills.coverage",
            references,
            "岗位技能要求尚未确认。",
            "缺少 confirmed 的 required_skills。",
        )
    required = _normalized_unique_strings(required_value)
    if not required:
        return _result(
            "skills.coverage",
            RuleStatus.MATCH,
            references,
            "岗位未声明必须技能。",
        )

    skill_items = profile.get("skills")
    candidate = (
        _normalized_unique_strings(
            item.get("name")
            for item in skill_items
            if isinstance(skill_items, list) and isinstance(item, dict)
        )
        if isinstance(skill_items, list)
        else []
    )
    if not candidate:
        return _unknown(
            "skills.coverage",
            references,
            "候选人技能信息尚未确认。",
            "缺少 confirmed 的 skills[*].name。",
        )

    candidate_set = set(candidate)
    covered = [skill for skill in required if skill in candidate_set]
    missing = [skill for skill in required if skill not in candidate_set]
    if not missing:
        return _result(
            "skills.coverage",
            RuleStatus.MATCH,
            references,
            f"已确认技能覆盖全部 {len(required)} 项岗位要求。",
        )
    suggestion = f"补充或核实未覆盖技能：{', '.join(missing)}。"
    if covered:
        return _result(
            "skills.coverage",
            RuleStatus.PARTIAL,
            references,
            f"已覆盖 {len(covered)}/{len(required)} 项岗位技能要求。",
            suggestion=suggestion,
        )
    return _result(
        "skills.coverage",
        RuleStatus.MISMATCH,
        references,
        "已确认技能未覆盖岗位声明的必须技能。",
        suggestion=suggestion,
    )


def _evaluate_experience(
    profile_version: CandidateProfile,
    requirement_version: JobRequirementSnapshot,
    profile: dict[str, Any],
    requirements: dict[str, Any],
) -> RuleResult:
    references = (
        _requirement_ref(requirement_version, "minimum_experience_years"),
        _profile_ref(profile_version, "experiences[*].start_date"),
        _profile_ref(profile_version, "experiences[*].end_date"),
    )
    minimum = requirements.get("minimum_experience_years")
    if isinstance(minimum, bool) or not isinstance(minimum, int):
        return _unknown(
            "experience.minimum_years",
            references,
            "岗位最低经验年限尚未确认。",
            "缺少 confirmed 的 minimum_experience_years。",
        )
    if minimum == 0:
        return _result(
            "experience.minimum_years",
            RuleStatus.MATCH,
            references,
            "岗位未要求最低工作经验年限。",
        )

    intervals, incomplete = _experience_intervals(profile.get("experiences"))
    if not intervals:
        return _unknown(
            "experience.minimum_years",
            references,
            "候选人经历年限无法由已确认日期计算。",
            "缺少完整 confirmed 的经历起止日期。",
        )
    days = _merged_interval_days(intervals)
    required_days = minimum * 365
    years = days / 365
    if days >= required_days:
        return _result(
            "experience.minimum_years",
            RuleStatus.MATCH,
            references,
            f"已确认经历约 {years:.1f} 年，达到岗位要求的 {minimum} 年。",
        )
    if incomplete:
        return _unknown(
            "experience.minimum_years",
            references,
            f"可计算的已确认经历约 {years:.1f} 年，暂未达到 {minimum} 年。",
            "仍有经历缺少完整 confirmed 起止日期，无法判定总年限。",
        )
    return _result(
        "experience.minimum_years",
        RuleStatus.MISMATCH,
        references,
        f"已确认经历约 {years:.1f} 年，低于岗位要求的 {minimum} 年。",
        suggestion="核实经历日期或准备说明可迁移经验。",
    )


def _evaluate_location_and_work_mode(
    profile_version: CandidateProfile,
    requirement_version: JobRequirementSnapshot,
    profile: dict[str, Any],
    requirements: dict[str, Any],
) -> RuleResult:
    references = (
        _requirement_ref(requirement_version, "location_requirement"),
        _requirement_ref(requirement_version, "work_mode"),
        _profile_ref(profile_version, "preferences.target_locations"),
        _profile_ref(profile_version, "preferences.accepts_remote"),
    )
    preferences = profile.get("preferences")
    preferences = preferences if isinstance(preferences, dict) else {}

    required_location = _normalized_string(requirements.get("location_requirement"))
    target_locations = preferences.get("target_locations")
    normalized_targets = (
        _normalized_unique_strings(target_locations) if isinstance(target_locations, list) else []
    )
    if required_location is None or not normalized_targets:
        location_status = RuleStatus.UNKNOWN
    elif required_location in set(normalized_targets):
        location_status = RuleStatus.MATCH
    else:
        location_status = RuleStatus.MISMATCH

    work_mode = _normalized_string(requirements.get("work_mode"))
    accepts_remote = preferences.get("accepts_remote")
    if work_mode is None or work_mode == "unknown":
        work_status = RuleStatus.UNKNOWN
    elif work_mode == "remote":
        work_status = (
            RuleStatus.MATCH
            if accepts_remote is True
            else RuleStatus.MISMATCH
            if accepts_remote is False
            else RuleStatus.UNKNOWN
        )
    elif work_mode in {"onsite", "hybrid"}:
        work_status = location_status
    else:
        work_status = RuleStatus.UNKNOWN

    if work_mode == "remote":
        overall_status = work_status
    else:
        components = (location_status, work_status)
        if RuleStatus.MISMATCH in components:
            overall_status = RuleStatus.MISMATCH
        elif components == (RuleStatus.MATCH, RuleStatus.MATCH):
            overall_status = RuleStatus.MATCH
        elif RuleStatus.MATCH in components:
            overall_status = RuleStatus.PARTIAL
        else:
            overall_status = RuleStatus.UNKNOWN

    reason = f"地点兼容性为 {location_status.value}，工作方式兼容性为 {work_status.value}。"
    if overall_status is RuleStatus.MISMATCH:
        return _result(
            "location_work_mode.compatibility",
            RuleStatus.MISMATCH,
            references,
            reason,
            suggestion="核实目标地点或工作方式偏好。",
        )
    if overall_status is RuleStatus.MATCH:
        return _result(
            "location_work_mode.compatibility",
            RuleStatus.MATCH,
            references,
            reason,
        )
    if overall_status is RuleStatus.PARTIAL:
        return _result(
            "location_work_mode.compatibility",
            RuleStatus.PARTIAL,
            references,
            reason,
            uncertainty="地点或工作方式仍有一项缺少 confirmed 输入。",
        )
    return _unknown(
        "location_work_mode.compatibility",
        references,
        reason,
        "缺少 confirmed 的地点要求、目标地点或工作方式偏好。",
    )


def _evaluate_degree(
    profile_version: CandidateProfile,
    requirement_version: JobRequirementSnapshot,
    profile: dict[str, Any],
    requirements: dict[str, Any],
) -> RuleResult:
    references = (
        _requirement_ref(requirement_version, "degree_requirement"),
        _profile_ref(profile_version, "education[*].degree"),
    )
    required_text = _normalized_string(requirements.get("degree_requirement"))
    if required_text is None:
        return _unknown(
            "degree.minimum",
            references,
            "岗位学历要求尚未确认。",
            "缺少 confirmed 的 degree_requirement。",
        )
    if required_text in {"不限", "无要求", "none", "not required"}:
        return _result(
            "degree.minimum",
            RuleStatus.MATCH,
            references,
            "岗位未设置最低学历要求。",
        )

    education = profile.get("education")
    degrees = (
        [
            value
            for item in education
            if isinstance(education, list)
            and isinstance(item, dict)
            and (value := _normalized_string(item.get("degree"))) is not None
        ]
        if isinstance(education, list)
        else []
    )
    if not degrees:
        return _unknown(
            "degree.minimum",
            references,
            "候选人学历信息尚未确认。",
            "缺少 confirmed 的 education[*].degree。",
        )
    if required_text in degrees:
        return _result(
            "degree.minimum",
            RuleStatus.MATCH,
            references,
            "已确认学历与岗位要求一致。",
        )

    required_rank = _degree_rank(required_text)
    ranked = [rank for degree in degrees if (rank := _degree_rank(degree)) is not None]
    if required_rank is None or not ranked:
        return _unknown(
            "degree.minimum",
            references,
            "现有学历文本无法按规则集确定等级关系。",
            "规则仅比较明确支持的学历名称，不推断未知表达。",
        )
    if max(ranked) >= required_rank:
        return _result(
            "degree.minimum",
            RuleStatus.MATCH,
            references,
            "已确认学历达到或高于岗位最低要求。",
        )
    if len(ranked) != len(degrees):
        return _unknown(
            "degree.minimum",
            references,
            "已识别学历低于岗位要求，但仍有未知学历表达。",
            "未知学历表达可能改变比较结果。",
        )
    return _result(
        "degree.minimum",
        RuleStatus.MISMATCH,
        references,
        "已确认最高学历低于岗位最低要求。",
        suggestion="核实岗位是否接受同等经验替代学历要求。",
    )


def _experience_intervals(value: Any) -> tuple[list[tuple[date, date]], bool]:
    if not isinstance(value, list) or not value:
        return [], True
    intervals: list[tuple[date, date]] = []
    incomplete = False
    for item in value:
        if not isinstance(item, dict):
            incomplete = True
            continue
        start = _parse_date(item.get("start_date"))
        end = _parse_date(item.get("end_date"))
        if start is None or end is None or end < start:
            incomplete = True
            continue
        intervals.append((start, end))
    return intervals, incomplete


def _merged_interval_days(intervals: list[tuple[date, date]]) -> int:
    ordered = sorted(intervals)
    merged: list[tuple[date, date]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return sum((end - start).days for start, end in merged)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _degree_rank(value: str) -> int | None:
    aliases = {
        "高中": 1,
        "中专": 1,
        "high school": 1,
        "大专": 2,
        "专科": 2,
        "associate": 2,
        "associate degree": 2,
        "本科": 3,
        "学士": 3,
        "bachelor": 3,
        "bachelor degree": 3,
        "bachelor's degree": 3,
        "bs": 3,
        "ba": 3,
        "硕士": 4,
        "研究生": 4,
        "master": 4,
        "master degree": 4,
        "master's degree": 4,
        "ms": 4,
        "ma": 4,
        "博士": 5,
        "phd": 5,
        "doctorate": 5,
    }
    return aliases.get(value)


def _normalized_unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list) and not hasattr(values, "__iter__"):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalized_string(value)
        if item is not None and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _normalized_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).casefold()
    return normalized or None


def _requirement_ref(snapshot: JobRequirementSnapshot, field_path: str) -> RuleInputReference:
    return RuleInputReference(
        source=RuleInputSource.JOB_REQUIREMENT_SNAPSHOT,
        object_id=snapshot.id,
        version=snapshot.version,
        field_path=field_path,
    )


def _profile_ref(profile: CandidateProfile, field_path: str) -> RuleInputReference:
    return RuleInputReference(
        source=RuleInputSource.CANDIDATE_PROFILE,
        object_id=profile.id,
        version=profile.version,
        field_path=field_path,
    )


def _unknown(
    rule_id: str,
    references: tuple[RuleInputReference, ...],
    reason: str,
    uncertainty: str,
) -> RuleResult:
    return _result(
        rule_id,
        RuleStatus.UNKNOWN,
        references,
        reason,
        uncertainty=uncertainty,
    )


def _result(
    rule_id: str,
    status: RuleStatus,
    references: tuple[RuleInputReference, ...],
    reason: str,
    *,
    uncertainty: str | None = None,
    suggestion: str | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        status=status,
        input_references=references,
        reason=reason,
        uncertainty=uncertainty,
        suggestion=suggestion,
    )
