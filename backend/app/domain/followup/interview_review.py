"""Versioned interview review facts and confirmation-safe memory candidates."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_REVIEW_TEXT = 8_000
MAX_REVIEW_ITEMS = 50


class MemoryCandidateKind(StrEnum):
    SKILL_GAP = "skill_gap"
    INTERVIEW_PATTERN = "interview_pattern"
    RESUME_ISSUE = "resume_issue"
    KNOWLEDGE_GAP = "knowledge_gap"


class MemoryCandidateStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class InterviewReview:
    id: UUID
    owner_id: UUID
    interview_case_id: UUID
    interview_case_version: int
    version: int
    questions: tuple[str, ...]
    answers: tuple[str, ...]
    self_assessment: str
    blockers: tuple[str, ...]
    outcome: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        interview_case_id: UUID,
        interview_case_version: int,
        version: int,
        questions: tuple[str, ...],
        answers: tuple[str, ...],
        self_assessment: str,
        blockers: tuple[str, ...],
        outcome: str,
        now: datetime | None = None,
    ) -> "InterviewReview":
        normalized_questions = _items(questions)
        normalized_answers = _items(answers)
        normalized_blockers = _items(blockers, allow_empty=True)
        assessment = _text(self_assessment, "self_assessment")
        result = _text(outcome, "outcome")
        if len(normalized_questions) != len(normalized_answers):
            raise DomainError(
                "Questions and answers must align", error_code=ErrorCode.INVALID_REPORT_CONTENT
            )
        if interview_case_version < 1 or version < 1 or not normalized_questions:
            raise DomainError(
                "Interview review input is invalid", error_code=ErrorCode.INVALID_VERSION
            )
        return cls(
            uuid4(),
            owner_id,
            interview_case_id,
            interview_case_version,
            version,
            normalized_questions,
            normalized_answers,
            assessment,
            normalized_blockers,
            result,
            _utc(now),
        )


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    id: UUID
    owner_id: UUID
    review_id: UUID
    review_version: int
    kind: MemoryCandidateKind
    text: str
    reason: str
    confidence: float | None
    unknown: bool
    suggested_action: str
    status: MemoryCandidateStatus
    source_id: UUID | None
    source_version: int | None
    artifact_id: UUID | None
    artifact_version: int | None
    created_at: datetime
    confirmed_at: datetime | None = None
    rejected_at: datetime | None = None

    @classmethod
    def propose(
        cls,
        *,
        owner_id: UUID,
        review_id: UUID,
        review_version: int,
        kind: MemoryCandidateKind,
        text: str,
        reason: str,
        confidence: float | None,
        unknown: bool,
        suggested_action: str,
        now: datetime | None = None,
    ) -> "MemoryCandidate":
        if review_version < 1:
            raise DomainError(
                "Candidate review version is invalid", error_code=ErrorCode.INVALID_VERSION
            )
        if confidence is not None and not 0 <= confidence <= 1:
            raise DomainError(
                "Candidate confidence is invalid", error_code=ErrorCode.INVALID_REPORT_CONTENT
            )
        return cls(
            uuid4(),
            owner_id,
            review_id,
            review_version,
            MemoryCandidateKind(kind),
            _text(text, "candidate text"),
            _text(reason, "candidate reason"),
            confidence,
            bool(unknown),
            _text(suggested_action, "suggested action"),
            MemoryCandidateStatus.PROPOSED,
            None,
            None,
            None,
            None,
            _utc(now),
        )

    def confirm(
        self,
        *,
        source_id: UUID,
        source_version: int,
        artifact_id: UUID,
        artifact_version: int,
        now: datetime | None = None,
    ) -> "MemoryCandidate":
        if self.status is not MemoryCandidateStatus.PROPOSED:
            raise DomainError(
                "Candidate cannot be confirmed",
                error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION,
            )
        return replace(
            self,
            status=MemoryCandidateStatus.CONFIRMED,
            source_id=source_id,
            source_version=source_version,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            confirmed_at=_utc(now),
        )

    def reject(self, now: datetime | None = None) -> "MemoryCandidate":
        if self.status is not MemoryCandidateStatus.PROPOSED:
            raise DomainError(
                "Candidate cannot be rejected", error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION
            )
        return replace(self, status=MemoryCandidateStatus.REJECTED, rejected_at=_utc(now))

    def revoke(self, now: datetime | None = None) -> "MemoryCandidate":
        if self.status is not MemoryCandidateStatus.CONFIRMED:
            raise DomainError(
                "Candidate cannot be revoked", error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION
            )
        return replace(
            self,
            status=MemoryCandidateStatus.REVOKED,
            source_id=None,
            source_version=None,
            artifact_id=None,
            artifact_version=None,
            rejected_at=_utc(now),
        )


def _text(value: str, name: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_REVIEW_TEXT:
        raise DomainError(f"{name} is invalid", error_code=ErrorCode.INVALID_REPORT_CONTENT)
    return normalized


def _items(values: tuple[str, ...], *, allow_empty: bool = False) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise DomainError("Review items are required", error_code=ErrorCode.INVALID_REPORT_CONTENT)
    if len(values) > MAX_REVIEW_ITEMS:
        raise DomainError("Too many review items", error_code=ErrorCode.INVALID_REPORT_CONTENT)
    return tuple(_text(value, "review item") for value in values)


def _utc(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    return timestamp.astimezone(timezone.utc)
