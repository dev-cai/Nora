"""Immutable deterministic DecisionReport and its report sections."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError

from .decision_case import DecisionCase
from .rules import RuleInputReference, RuleInputSource, RuleResult, RuleSetEvaluation, RuleStatus

MAX_GENERATOR_VERSION_LENGTH = 100
MAX_REPORT_TEXT_LENGTH = 1_000


class ReportSection(StrEnum):
    """Stable semantic sections of the deterministic report DTO."""

    FACT = "fact"
    RULE_RESULT = "rule_result"
    UNKNOWN = "unknown"
    RECOMMENDATION = "recommendation"
    CITATION = "citation"


@dataclass(frozen=True, slots=True)
class ReportCitation:
    """A field-level pointer into one immutable business input."""

    citation_id: str
    source: RuleInputSource
    object_id: UUID
    version: int
    field_path: str


@dataclass(frozen=True, slots=True)
class ReportFact:
    """A confirmed fact represented by a rule input reference."""

    fact_id: str
    label: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportRuleResult:
    """A versioned rule outcome embedded into a published report."""

    rule_id: str
    rule_version: str
    status: RuleStatus
    reason: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportUnknown:
    """An input gap or uncertainty that remains explicit."""

    unknown_id: str
    reason: str
    detail: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportRecommendation:
    """A deterministic next action derived from a rule result."""

    recommendation_id: str
    action: str
    rationale: str
    source_rule_id: str


@dataclass(frozen=True, slots=True)
class MatchSummary:
    """Counts of the four stable deterministic result states."""

    match: int
    partial: int
    mismatch: int
    unknown: int


@dataclass(frozen=True, slots=True)
class DecisionReport:
    """An immutable, versioned deterministic report business fact."""

    id: UUID
    owner_id: UUID
    decision_case_id: UUID
    version: int
    rule_set_version: str
    generator_version: str
    summary: MatchSummary
    facts: tuple[ReportFact, ...]
    rule_results: tuple[ReportRuleResult, ...]
    unknowns: tuple[ReportUnknown, ...]
    recommendations: tuple[ReportRecommendation, ...]
    citations: tuple[ReportCitation, ...]
    satisfied_conditions: tuple[str, ...]
    gaps: tuple[str, ...]
    risks: tuple[str, ...]
    next_steps: tuple[str, ...]
    generated_at: datetime

    @staticmethod
    def normalize_generator_version(value: str) -> str:
        """Return the canonical generator identity used for idempotency."""

        return _normalize_text(
            value,
            MAX_GENERATOR_VERSION_LENGTH,
            "invalid_report_generator_version",
        )

    @classmethod
    def generate(
        cls,
        *,
        decision_case: DecisionCase,
        evaluation: RuleSetEvaluation,
        version: int,
        generator_version: str,
        now: datetime | None = None,
    ) -> "DecisionReport":
        """Publish a report from the exact rule evaluation fixed by DecisionCase."""

        if evaluation.decision_case_id != decision_case.id:
            raise DomainError(
                "Rule evaluation does not belong to the decision case",
                error_code="report_input_mismatch",
            )
        if evaluation.rule_set_version != decision_case.rule_set_version:
            raise DomainError(
                "Rule evaluation uses a different rule set",
                error_code="report_input_mismatch",
            )
        report_version = _positive_version(version)
        normalized_generator = cls.normalize_generator_version(generator_version)
        citations = _citations(evaluation.results)
        citation_ids = {
            _reference_key(reference): citation.citation_id
            for citation in citations
            for reference in (
                RuleInputReference(
                    source=citation.source,
                    object_id=citation.object_id,
                    version=citation.version,
                    field_path=citation.field_path,
                ),
            )
        }
        rule_results = tuple(
            ReportRuleResult(
                rule_id=result.rule_id,
                rule_version=result.rule_version,
                status=result.status,
                reason=_bounded(result.reason),
                citation_ids=tuple(
                    citation_ids[_reference_key(reference)] for reference in result.input_references
                ),
            )
            for result in evaluation.results
        )
        confirmed_citation_ids = tuple(
            dict.fromkeys(
                citation_id
                for result, rule_result in zip(evaluation.results, rule_results, strict=True)
                if result.status in {RuleStatus.MATCH, RuleStatus.MISMATCH}
                for citation_id in rule_result.citation_ids
            )
        )
        citations_by_id = {item.citation_id: item for item in citations}
        facts = tuple(
            ReportFact(
                fact_id=f"fact:{citation_id}",
                label=_bounded(
                    f"已确认输入：{citations_by_id[citation_id].source.value}."
                    f"{citations_by_id[citation_id].field_path}"
                ),
                citation_ids=(citation_id,),
            )
            for citation_id in confirmed_citation_ids
        )
        unknowns = tuple(
            ReportUnknown(
                unknown_id=f"unknown:{result.rule_id}",
                reason=_bounded(result.reason),
                detail=_bounded(result.uncertainty or "当前输入不足以确定结果。"),
                citation_ids=rule_result.citation_ids,
            )
            for result, rule_result in zip(evaluation.results, rule_results, strict=True)
            if result.status is RuleStatus.UNKNOWN
        )
        recommendations = tuple(
            ReportRecommendation(
                recommendation_id=f"recommendation:{result.rule_id}",
                action=_bounded(result.suggestion or _default_action(result.status)),
                rationale=_bounded(result.reason),
                source_rule_id=result.rule_id,
            )
            for result in evaluation.results
            if result.status is not RuleStatus.MATCH or result.suggestion is not None
        )
        statuses = [result.status for result in evaluation.results]
        return cls(
            id=uuid4(),
            owner_id=decision_case.owner_id,
            decision_case_id=decision_case.id,
            version=report_version,
            rule_set_version=evaluation.rule_set_version,
            generator_version=normalized_generator,
            summary=MatchSummary(
                match=statuses.count(RuleStatus.MATCH),
                partial=statuses.count(RuleStatus.PARTIAL),
                mismatch=statuses.count(RuleStatus.MISMATCH),
                unknown=statuses.count(RuleStatus.UNKNOWN),
            ),
            facts=facts,
            rule_results=rule_results,
            unknowns=unknowns,
            recommendations=recommendations,
            citations=citations,
            satisfied_conditions=tuple(
                result.reason for result in evaluation.results if result.status is RuleStatus.MATCH
            ),
            gaps=tuple(
                result.reason
                for result in evaluation.results
                if result.status in {RuleStatus.PARTIAL, RuleStatus.MISMATCH}
            ),
            risks=tuple(
                result.uncertainty or result.reason
                for result in evaluation.results
                if result.status in {RuleStatus.MISMATCH, RuleStatus.UNKNOWN}
            ),
            next_steps=tuple(item.action for item in recommendations),
            generated_at=_utc_timestamp(now),
        )

    @classmethod
    def restore(
        cls,
        *,
        report_id: UUID,
        owner_id: UUID,
        decision_case_id: UUID,
        version: int,
        rule_set_version: str,
        generator_version: str,
        content: dict[str, Any],
        generated_at: datetime,
    ) -> "DecisionReport":
        """Restore and validate an immutable report persisted as structured JSON."""

        try:
            summary = MatchSummary(**content["summary"])
            citations = tuple(
                ReportCitation(
                    citation_id=item["citation_id"],
                    source=RuleInputSource(item["source"]),
                    object_id=UUID(item["object_id"]),
                    version=item["version"],
                    field_path=item["field_path"],
                )
                for item in content[ReportSection.CITATION.value]
            )
            facts = tuple(
                ReportFact(
                    fact_id=item["fact_id"],
                    label=item["label"],
                    citation_ids=tuple(item["citation_ids"]),
                )
                for item in content[ReportSection.FACT.value]
            )
            rule_results = tuple(
                ReportRuleResult(
                    rule_id=item["rule_id"],
                    rule_version=item["rule_version"],
                    status=RuleStatus(item["status"]),
                    reason=item["reason"],
                    citation_ids=tuple(item["citation_ids"]),
                )
                for item in content[ReportSection.RULE_RESULT.value]
            )
            unknowns = tuple(
                ReportUnknown(
                    unknown_id=item["unknown_id"],
                    reason=item["reason"],
                    detail=item["detail"],
                    citation_ids=tuple(item["citation_ids"]),
                )
                for item in content[ReportSection.UNKNOWN.value]
            )
            recommendations = tuple(
                ReportRecommendation(**item) for item in content[ReportSection.RECOMMENDATION.value]
            )
            report = cls(
                id=report_id,
                owner_id=owner_id,
                decision_case_id=decision_case_id,
                version=_positive_version(version),
                rule_set_version=_normalize_text(
                    rule_set_version, 100, "invalid_report_rule_set_version"
                ),
                generator_version=_normalize_text(
                    generator_version,
                    MAX_GENERATOR_VERSION_LENGTH,
                    "invalid_report_generator_version",
                ),
                summary=summary,
                facts=facts,
                rule_results=rule_results,
                unknowns=unknowns,
                recommendations=recommendations,
                citations=citations,
                satisfied_conditions=tuple(content["satisfied_conditions"]),
                gaps=tuple(content["gaps"]),
                risks=tuple(content["risks"]),
                next_steps=tuple(content["next_steps"]),
                generated_at=_utc_timestamp(generated_at),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "Stored report content is invalid", error_code="invalid_report_content"
            ) from exc
        report._validate_content()
        return report

    @property
    def content(self) -> dict[str, Any]:
        """Return the immutable report sections as a safe JSON-compatible copy."""

        return json.loads(
            json.dumps(
                {
                    "summary": asdict(self.summary),
                    ReportSection.FACT.value: [asdict(item) for item in self.facts],
                    ReportSection.RULE_RESULT.value: [asdict(item) for item in self.rule_results],
                    ReportSection.UNKNOWN.value: [asdict(item) for item in self.unknowns],
                    ReportSection.RECOMMENDATION.value: [
                        asdict(item) for item in self.recommendations
                    ],
                    ReportSection.CITATION.value: [
                        {
                            **asdict(item),
                            "source": item.source.value,
                            "object_id": str(item.object_id),
                        }
                        for item in self.citations
                    ],
                    "satisfied_conditions": list(self.satisfied_conditions),
                    "gaps": list(self.gaps),
                    "risks": list(self.risks),
                    "next_steps": list(self.next_steps),
                },
                ensure_ascii=False,
            )
        )

    def _validate_content(self) -> None:
        citation_ids = {item.citation_id for item in self.citations}
        if len(citation_ids) != len(self.citations) or not self.rule_results:
            raise DomainError("Report content is invalid", error_code="invalid_report_content")
        referenced_ids = {citation_id for item in self.facts for citation_id in item.citation_ids}
        referenced_ids.update(
            citation_id for item in self.rule_results for citation_id in item.citation_ids
        )
        referenced_ids.update(
            citation_id for item in self.unknowns for citation_id in item.citation_ids
        )
        if not referenced_ids <= citation_ids:
            raise DomainError("Report citation is invalid", error_code="invalid_report_content")


def _citations(results: tuple[RuleResult, ...]) -> tuple[ReportCitation, ...]:
    references: dict[tuple[str, str, int, str], RuleInputReference] = {}
    for result in results:
        for reference in result.input_references:
            references.setdefault(_reference_key(reference), reference)
    return tuple(
        ReportCitation(
            citation_id=f"citation:{index}",
            source=reference.source,
            object_id=reference.object_id,
            version=reference.version,
            field_path=reference.field_path,
        )
        for index, reference in enumerate(references.values(), start=1)
    )


def _reference_key(reference: RuleInputReference) -> tuple[str, str, int, str]:
    return (
        reference.source.value,
        str(reference.object_id),
        reference.version,
        reference.field_path,
    )


def _default_action(status: RuleStatus) -> str:
    return {
        RuleStatus.PARTIAL: "补充部分匹配项并重新评估。",
        RuleStatus.MISMATCH: "评估差距是否可接受，再决定是否投入。",
        RuleStatus.UNKNOWN: "补充或确认缺失输入后重新生成报告。",
        RuleStatus.MATCH: "保持当前已确认信息。",
    }[status]


def _positive_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainError("Report version must be positive", error_code="invalid_report_version")
    return value


def _normalize_text(value: str, maximum: int, error_code: str) -> str:
    if not isinstance(value, str):
        raise DomainError("Report value must be text", error_code=error_code)
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise DomainError(
            f"Report value must contain 1-{maximum} characters", error_code=error_code
        )
    return normalized


def _bounded(value: str) -> str:
    return _normalize_text(value, MAX_REPORT_TEXT_LENGTH, "invalid_report_content")


def _utc_timestamp(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return timestamp.astimezone(timezone.utc)
