"""Immutable, evidence-aware interview preparation plans."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode


class PreparationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class PreparationCitation:
    citation_id: UUID
    source_id: UUID
    source_version: int
    locator: str
    excerpt: str
    score: float


@dataclass(frozen=True, slots=True)
class PreparationTopic:
    topic_id: str
    title: str
    priority: PreparationPriority
    reason: str
    estimated_effort_minutes: int
    status: str
    suggestion: str
    citation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class InterviewPreparation:
    id: UUID
    owner_id: UUID
    interview_case_id: UUID
    interview_case_version: int
    application_record_id: UUID
    decision_case_id: UUID
    decision_report_id: UUID | None
    decision_report_version: int | None
    version: int
    generator_version: str
    prompt_version: str
    generation_identity: str
    topics: tuple[PreparationTopic, ...]
    citations: tuple[PreparationCitation, ...]
    created_at: datetime

    @classmethod
    def publish(
        cls,
        *,
        owner_id: UUID,
        interview_case_id: UUID,
        interview_case_version: int,
        application_record_id: UUID,
        decision_case_id: UUID,
        decision_report_id: UUID | None,
        decision_report_version: int | None,
        version: int,
        generator_version: str,
        prompt_version: str,
        topics: tuple[PreparationTopic, ...],
        citations: tuple[PreparationCitation, ...],
        now: datetime | None = None,
    ) -> "InterviewPreparation":
        if version < 1 or interview_case_version < 1 or not topics:
            raise DomainError("Preparation input is invalid", error_code=ErrorCode.INVALID_VERSION)
        citation_ids = {item.citation_id for item in citations}
        for topic in topics:
            if any(item not in citation_ids for item in topic.citation_ids):
                raise DomainError(
                    "Preparation citation is invalid", error_code=ErrorCode.INVALID_REPORT_CONTENT
                )
        identity_payload = {
            "owner_id": str(owner_id),
            "interview_case_id": str(interview_case_id),
            "interview_case_version": interview_case_version,
            "version": version,
            "generator_version": generator_version,
            "prompt_version": prompt_version,
        }
        identity = sha256(json.dumps(identity_payload, sort_keys=True).encode()).hexdigest()
        timestamp = now or datetime.now(timezone.utc)
        return cls(
            uuid4(),
            owner_id,
            interview_case_id,
            interview_case_version,
            application_record_id,
            decision_case_id,
            decision_report_id,
            decision_report_version,
            version,
            generator_version,
            prompt_version,
            identity,
            tuple(topics),
            tuple(citations),
            timestamp.astimezone(timezone.utc),
        )

    @classmethod
    def restore(
        cls,
        *,
        preparation_id: UUID,
        owner_id: UUID,
        interview_case_id: UUID,
        interview_case_version: int,
        application_record_id: UUID,
        decision_case_id: UUID,
        decision_report_id: UUID | None,
        decision_report_version: int | None,
        version: int,
        generator_version: str,
        prompt_version: str,
        generation_identity: str,
        content: dict[str, Any],
        created_at: datetime,
    ) -> "InterviewPreparation":
        try:
            citations = tuple(
                PreparationCitation(
                    citation_id=UUID(item["citation_id"]),
                    source_id=UUID(item["source_id"]),
                    source_version=int(item["source_version"]),
                    locator=str(item["locator"]),
                    excerpt=str(item["excerpt"]),
                    score=float(item["score"]),
                )
                for item in content["citations"]
            )
            topics = tuple(
                PreparationTopic(
                    topic_id=str(item["topic_id"]),
                    title=str(item["title"]),
                    priority=PreparationPriority(item["priority"]),
                    reason=str(item["reason"]),
                    estimated_effort_minutes=int(item["estimated_effort_minutes"]),
                    status=str(item["status"]),
                    suggestion=str(item["suggestion"]),
                    citation_ids=tuple(UUID(value) for value in item["citation_ids"]),
                )
                for item in content["topics"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "Stored preparation is invalid", error_code=ErrorCode.INVALID_REPORT_CONTENT
            ) from exc
        value = cls(
            preparation_id,
            owner_id,
            interview_case_id,
            interview_case_version,
            application_record_id,
            decision_case_id,
            decision_report_id,
            decision_report_version,
            version,
            generator_version,
            prompt_version,
            generation_identity,
            topics,
            citations,
            created_at.astimezone(timezone.utc),
        )
        citation_ids = {item.citation_id for item in citations}
        if any(item not in citation_ids for topic in topics for item in topic.citation_ids):
            raise DomainError(
                "Stored preparation citation is invalid",
                error_code=ErrorCode.INVALID_REPORT_CONTENT,
            )
        return value

    @property
    def content(self) -> dict[str, object]:
        return {
            "topics": [
                asdict(item)
                | {
                    "priority": item.priority.value,
                    "citation_ids": [str(x) for x in item.citation_ids],
                }
                for item in self.topics
            ],
            "citations": [
                {
                    **asdict(item),
                    "citation_id": str(item.citation_id),
                    "source_id": str(item.source_id),
                }
                for item in self.citations
            ],
        }
