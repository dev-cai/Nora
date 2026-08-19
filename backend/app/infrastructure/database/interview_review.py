"""Persistence adapters for interview reviews and confirmation-safe candidates."""

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.followup import (
    InterviewReview,
    MemoryCandidate,
    MemoryCandidateKind,
    MemoryCandidateStatus,
)
from app.infrastructure.database.base import Base


class InterviewReviewRecord(Base):
    __tablename__ = "interview_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["interview_case_id", "interview_case_version", "owner_id"],
            ["interview_cases.id", "interview_cases.version", "interview_cases.owner_id"],
            name="fk_interview_review_case_owner",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interview_case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    interview_case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryCandidateRecord(Base):
    __tablename__ = "memory_candidates"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    unknown: Mapped[bool] = mapped_column(nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _review_domain(record: InterviewReviewRecord) -> InterviewReview:
    content = record.content
    return InterviewReview(
        record.id,
        record.owner_id,
        record.interview_case_id,
        record.interview_case_version,
        record.version,
        tuple(cast(list[str], content["questions"])),
        tuple(cast(list[str], content["answers"])),
        str(content["self_assessment"]),
        tuple(cast(list[str], content.get("blockers", []))),
        str(content["outcome"]),
        _utc(record.created_at),
    )


def _candidate_domain(record: MemoryCandidateRecord) -> MemoryCandidate:
    return MemoryCandidate(
        record.id,
        record.owner_id,
        record.review_id,
        record.review_version,
        MemoryCandidateKind(record.kind),
        record.text,
        record.reason,
        record.confidence,
        record.unknown,
        record.suggested_action,
        MemoryCandidateStatus(record.status),
        record.source_id,
        record.source_version,
        record.artifact_id,
        record.artifact_version,
        _utc(record.created_at),
        _utc(record.confirmed_at) if record.confirmed_at else None,
        _utc(record.rejected_at) if record.rejected_at else None,
    )


class SqlAlchemyInterviewReviewRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session, self.owner_id = session, owner_id

    async def next_version(self, interview_case_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(InterviewReviewRecord.version)).where(
                InterviewReviewRecord.owner_id == self.owner_id,
                InterviewReviewRecord.interview_case_id == interview_case_id,
            )
        )
        return int(latest or 0) + 1

    async def add(self, review: InterviewReview) -> InterviewReview:
        if review.owner_id != self.owner_id:
            raise InfrastructureError(
                "Review is outside user scope", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        self.session.add(
            InterviewReviewRecord(
                id=review.id,
                owner_id=review.owner_id,
                interview_case_id=review.interview_case_id,
                interview_case_version=review.interview_case_version,
                version=review.version,
                content={
                    "questions": list(review.questions),
                    "answers": list(review.answers),
                    "self_assessment": review.self_assessment,
                    "blockers": list(review.blockers),
                    "outcome": review.outcome,
                },
                created_at=review.created_at,
            )
        )
        await self.session.flush()
        return review

    async def get_latest(self, interview_case_id: UUID) -> InterviewReview | None:
        record = await self.session.scalar(
            select(InterviewReviewRecord)
            .where(
                InterviewReviewRecord.owner_id == self.owner_id,
                InterviewReviewRecord.interview_case_id == interview_case_id,
            )
            .order_by(InterviewReviewRecord.version.desc())
            .limit(1)
        )
        return _review_domain(record) if record else None

    async def list_versions(self, interview_case_id: UUID) -> list[InterviewReview]:
        records = await self.session.scalars(
            select(InterviewReviewRecord)
            .where(
                InterviewReviewRecord.owner_id == self.owner_id,
                InterviewReviewRecord.interview_case_id == interview_case_id,
            )
            .order_by(InterviewReviewRecord.version.desc())
        )
        return [_review_domain(record) for record in records]

    async def commit(self) -> None:
        await self.session.commit()


class SqlAlchemyMemoryCandidateRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session, self.owner_id = session, owner_id

    async def add(self, candidate: MemoryCandidate) -> MemoryCandidate:
        self._check_owner(candidate)
        self.session.add(MemoryCandidateRecord(**_candidate_values(candidate)))
        await self.session.flush()
        return candidate

    async def update(self, candidate: MemoryCandidate) -> MemoryCandidate:
        self._check_owner(candidate)
        record = await self.session.scalar(
            select(MemoryCandidateRecord)
            .where(
                MemoryCandidateRecord.id == candidate.id,
                MemoryCandidateRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if record is None:
            raise InfrastructureError("Candidate not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        for name, value in _candidate_values(candidate).items():
            setattr(record, name, value)
        await self.session.flush()
        return candidate

    async def get_by_id(self, candidate_id: UUID) -> MemoryCandidate | None:
        record = await self.session.scalar(
            select(MemoryCandidateRecord).where(
                MemoryCandidateRecord.id == candidate_id,
                MemoryCandidateRecord.owner_id == self.owner_id,
            )
        )
        return _candidate_domain(record) if record else None

    async def list_for_review(self, review_id: UUID) -> list[MemoryCandidate]:
        records = await self.session.scalars(
            select(MemoryCandidateRecord)
            .where(
                MemoryCandidateRecord.owner_id == self.owner_id,
                MemoryCandidateRecord.review_id == review_id,
            )
            .order_by(MemoryCandidateRecord.created_at)
        )
        return [_candidate_domain(record) for record in records]

    async def commit(self) -> None:
        await self.session.commit()

    def _check_owner(self, candidate: MemoryCandidate) -> None:
        if candidate.owner_id != self.owner_id:
            raise InfrastructureError(
                "Candidate is outside user scope", error_code=ErrorCode.ENTITY_NOT_FOUND
            )


def _candidate_values(value: MemoryCandidate) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "review_id": value.review_id,
        "review_version": value.review_version,
        "kind": value.kind.value,
        "text": value.text,
        "reason": value.reason,
        "confidence": value.confidence,
        "unknown": value.unknown,
        "suggested_action": value.suggested_action,
        "status": value.status.value,
        "source_id": value.source_id,
        "source_version": value.source_version,
        "artifact_id": value.artifact_id,
        "artifact_version": value.artifact_version,
        "created_at": value.created_at,
        "confirmed_at": value.confirmed_at,
        "rejected_at": value.rejected_at,
    }


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
