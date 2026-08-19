"""Immutable AI-assisted job-fit analysis with strict fixed-input citations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_ANALYSIS_TEXT_LENGTH = 1_000
MAX_ANALYSIS_ITEMS = 20
MAX_IDENTITY_TEXT_LENGTH = 100


class JobFitLevel(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


class JobFitCitationSource(StrEnum):
    CANDIDATE_PROFILE = "candidate_profile"
    RESUME_VERSION = "resume_version"
    JOB_POSTING = "job_posting"
    JOB_REQUIREMENT_SNAPSHOT = "job_requirement_snapshot"
    DECISION_REPORT = "decision_report"
    COMPANY_SNAPSHOT = "company_snapshot"


@dataclass(frozen=True, slots=True)
class JobFitCitation:
    citation_id: str
    source: JobFitCitationSource
    object_id: UUID
    version: int
    field_path: str

    @property
    def identity(self) -> tuple[str, UUID, int, str]:
        return (self.source.value, self.object_id, self.version, self.field_path)


@dataclass(frozen=True, slots=True)
class JobFitInsight:
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JobFitAnalysis:
    id: UUID
    owner_id: UUID
    report_id: UUID
    report_version: int
    decision_case_id: UUID
    version: int
    prompt_version: str
    provider: str
    model: str
    generator_version: str
    generation_identity: str
    overall_fit: JobFitLevel
    overall_fit_reason: JobFitInsight
    strong_matches: tuple[JobFitInsight, ...]
    transferable_evidence: tuple[JobFitInsight, ...]
    critical_gaps: tuple[JobFitInsight, ...]
    non_blocking_gaps: tuple[JobFitInsight, ...]
    resume_actions: tuple[JobFitInsight, ...]
    project_deep_dive_risks: tuple[JobFitInsight, ...]
    interview_focus: tuple[JobFitInsight, ...]
    unknowns: tuple[JobFitInsight, ...]
    citations: tuple[JobFitCitation, ...]
    generated_at: datetime

    @staticmethod
    def generation_key(
        *,
        owner_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        fixed_inputs: tuple[tuple[str, UUID, int], ...],
        prompt_version: str,
        provider: str,
        model: str,
        generator_version: str,
    ) -> str:
        payload = {
            "decision_case_id": str(decision_case_id),
            "fixed_inputs": [
                {"source": source, "object_id": str(object_id), "version": version}
                for source, object_id, version in fixed_inputs
            ],
            "generator_version": _identity_text(generator_version),
            "model": _identity_text(model),
            "owner_id": str(owner_id),
            "prompt_version": _identity_text(prompt_version),
            "provider": _identity_text(provider),
            "report_id": str(report_id),
            "report_version": _positive(report_version),
        }
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return sha256(encoded.encode()).hexdigest()

    @classmethod
    def publish(
        cls,
        *,
        owner_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        version: int,
        prompt_version: str,
        provider: str,
        model: str,
        generator_version: str,
        generation_identity: str,
        overall_fit: JobFitLevel,
        overall_fit_reason: JobFitInsight,
        strong_matches: tuple[JobFitInsight, ...],
        transferable_evidence: tuple[JobFitInsight, ...],
        critical_gaps: tuple[JobFitInsight, ...],
        non_blocking_gaps: tuple[JobFitInsight, ...],
        resume_actions: tuple[JobFitInsight, ...],
        project_deep_dive_risks: tuple[JobFitInsight, ...],
        interview_focus: tuple[JobFitInsight, ...],
        unknowns: tuple[JobFitInsight, ...],
        citations: tuple[JobFitCitation, ...],
        allowed_citations: frozenset[tuple[str, UUID, int, str]],
        now: datetime | None = None,
    ) -> "JobFitAnalysis":
        analysis = cls(
            id=uuid4(),
            owner_id=owner_id,
            report_id=report_id,
            report_version=_positive(report_version),
            decision_case_id=decision_case_id,
            version=_positive(version),
            prompt_version=_identity_text(prompt_version),
            provider=_identity_text(provider),
            model=_identity_text(model),
            generator_version=_identity_text(generator_version),
            generation_identity=_digest(generation_identity),
            overall_fit=JobFitLevel(overall_fit),
            overall_fit_reason=_normalize_insight(overall_fit_reason),
            strong_matches=_normalize_insights(strong_matches),
            transferable_evidence=_normalize_insights(transferable_evidence),
            critical_gaps=_normalize_insights(critical_gaps),
            non_blocking_gaps=_normalize_insights(non_blocking_gaps),
            resume_actions=_normalize_insights(resume_actions),
            project_deep_dive_risks=_normalize_insights(project_deep_dive_risks),
            interview_focus=_normalize_insights(interview_focus),
            unknowns=_normalize_insights(unknowns),
            citations=citations,
            generated_at=_utc(now),
        )
        analysis._validate_content(allowed_citations=allowed_citations)
        return analysis

    @classmethod
    def restore(
        cls,
        *,
        analysis_id: UUID,
        owner_id: UUID,
        report_id: UUID,
        report_version: int,
        decision_case_id: UUID,
        version: int,
        prompt_version: str,
        provider: str,
        model: str,
        generator_version: str,
        generation_identity: str,
        content: dict[str, Any],
        generated_at: datetime,
    ) -> "JobFitAnalysis":
        try:
            citations = tuple(
                JobFitCitation(
                    citation_id=item["citation_id"],
                    source=JobFitCitationSource(item["source"]),
                    object_id=UUID(item["object_id"]),
                    version=item["version"],
                    field_path=item["field_path"],
                )
                for item in content["citations"]
            )

            def insights(name: str) -> tuple[JobFitInsight, ...]:
                return tuple(
                    JobFitInsight(text=item["text"], citation_ids=tuple(item["citation_ids"]))
                    for item in content[name]
                )

            reason = content["overall_fit_reason"]
            analysis = cls(
                id=analysis_id,
                owner_id=owner_id,
                report_id=report_id,
                report_version=_positive(report_version),
                decision_case_id=decision_case_id,
                version=_positive(version),
                prompt_version=_identity_text(prompt_version),
                provider=_identity_text(provider),
                model=_identity_text(model),
                generator_version=_identity_text(generator_version),
                generation_identity=_digest(generation_identity),
                overall_fit=JobFitLevel(content["overall_fit"]),
                overall_fit_reason=JobFitInsight(
                    text=reason["text"], citation_ids=tuple(reason["citation_ids"])
                ),
                strong_matches=insights("strong_matches"),
                transferable_evidence=insights("transferable_evidence"),
                critical_gaps=insights("critical_gaps"),
                non_blocking_gaps=insights("non_blocking_gaps"),
                resume_actions=insights("resume_actions"),
                project_deep_dive_risks=insights("project_deep_dive_risks"),
                interview_focus=insights("interview_focus"),
                unknowns=insights("unknowns"),
                citations=citations,
                generated_at=_utc(generated_at),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "Stored job-fit analysis is invalid", error_code=ErrorCode.INVALID_REPORT_CONTENT
            ) from exc
        analysis._validate_content(
            allowed_citations=frozenset(citation.identity for citation in citations)
        )
        return analysis

    @property
    def content(self) -> dict[str, Any]:
        def serialized(items: tuple[JobFitInsight, ...]) -> list[dict[str, Any]]:
            return [asdict(item) for item in items]

        return {
            "overall_fit": self.overall_fit.value,
            "overall_fit_reason": asdict(self.overall_fit_reason),
            "strong_matches": serialized(self.strong_matches),
            "transferable_evidence": serialized(self.transferable_evidence),
            "critical_gaps": serialized(self.critical_gaps),
            "non_blocking_gaps": serialized(self.non_blocking_gaps),
            "resume_actions": serialized(self.resume_actions),
            "project_deep_dive_risks": serialized(self.project_deep_dive_risks),
            "interview_focus": serialized(self.interview_focus),
            "unknowns": serialized(self.unknowns),
            "citations": [
                {
                    **asdict(item),
                    "source": item.source.value,
                    "object_id": str(item.object_id),
                }
                for item in self.citations
            ],
        }

    def _validate_content(
        self, *, allowed_citations: frozenset[tuple[str, UUID, int, str]]
    ) -> None:
        if not self.citations:
            _invalid_output("At least one fixed-input citation is required")
        by_id = {item.citation_id: item for item in self.citations}
        if len(by_id) != len(self.citations):
            _invalid_output("Citation ids must be unique")
        for citation in self.citations:
            if citation.identity not in allowed_citations:
                _invalid_output("Citation is outside the fixed analysis inputs")
            _bounded(citation.citation_id, 100)
            _bounded(citation.field_path, 500)
            _positive(citation.version)

        groups = (
            (self.overall_fit_reason,),
            self.strong_matches,
            self.transferable_evidence,
            self.critical_gaps,
            self.non_blocking_gaps,
            self.resume_actions,
            self.project_deep_dive_risks,
            self.interview_focus,
            self.unknowns,
        )
        referenced: set[str] = set()
        for group in groups:
            if len(group) > MAX_ANALYSIS_ITEMS:
                _invalid_output("Analysis section contains too many items")
            for insight in group:
                _bounded(insight.text, MAX_ANALYSIS_TEXT_LENGTH)
                if not insight.citation_ids:
                    _invalid_output("Every inference or recommendation requires a citation")
                if len(set(insight.citation_ids)) != len(insight.citation_ids):
                    _invalid_output("Insight citation ids must be unique")
                if any(citation_id not in by_id for citation_id in insight.citation_ids):
                    _invalid_output("Insight contains an unresolved citation")
                referenced.update(insight.citation_ids)
        if referenced != set(by_id):
            _invalid_output("Citations must be used by an analysis item")


def _invalid_output(message: str) -> None:
    raise DomainError(message, error_code=ErrorCode.MODEL_OUTPUT_INVALID)


def _bounded(value: str, maximum: int) -> str:
    if not isinstance(value, str):
        _invalid_output("Analysis text must be a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        _invalid_output("Analysis text is blank or too long")
    return normalized


def _normalize_insight(value: JobFitInsight) -> JobFitInsight:
    return JobFitInsight(
        text=_bounded(value.text, MAX_ANALYSIS_TEXT_LENGTH),
        citation_ids=value.citation_ids,
    )


def _normalize_insights(values: tuple[JobFitInsight, ...]) -> tuple[JobFitInsight, ...]:
    return tuple(_normalize_insight(value) for value in values)


def _identity_text(value: str) -> str:
    return _bounded(value, MAX_IDENTITY_TEXT_LENGTH)


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid_output("Analysis version must be positive")
    return value


def _digest(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        _invalid_output("Analysis generation identity is invalid")
    return normalized


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError(
            "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
        )
    return result.astimezone(timezone.utc)


__all__ = (
    "JobFitAnalysis",
    "JobFitCitation",
    "JobFitCitationSource",
    "JobFitInsight",
    "JobFitLevel",
)
