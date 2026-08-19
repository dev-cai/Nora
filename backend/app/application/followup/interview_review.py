"""Interview review generation and confirmation-safe memory flow."""

from dataclasses import dataclass
from uuid import UUID

from app.application.knowledge import (
    ArtifactService,
    CreateSourceCommand,
    KnowledgeRagService,
    UploadArtifactCommand,
)
from app.application.model import InterviewReviewAnalysis, MemoryCandidateSuggestion
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.followup import (
    InterviewCase,
    InterviewReview,
    MemoryCandidate,
    MemoryCandidateKind,
)
from app.domain.governance import AuditAction, AuditEvent
from app.domain.knowledge import ArtifactKind, SourceKind
from app.ports.followup import (
    InterviewCaseRepository,
    InterviewReviewRepository,
    MemoryCandidateRepository,
)
from app.ports.governance import AuditEventRepository
from app.ports.model import ModelError, ModelPort, ModelRequest

PROMPT_VERSION = "interview-review-memory-v1"
GENERATOR_VERSION = "interview-review-v1"


@dataclass(frozen=True, slots=True)
class CreateInterviewReviewResult:
    review: InterviewReview
    candidates: tuple[MemoryCandidate, ...]


class InterviewReviewUseCases:
    def __init__(
        self,
        reviews: InterviewReviewRepository,
        candidates: MemoryCandidateRepository,
        interviews: InterviewCaseRepository,
        model: ModelPort | None,
        artifacts: ArtifactService,
        rag: KnowledgeRagService,
        audits: AuditEventRepository,
    ) -> None:
        self.reviews = reviews
        self.candidates = candidates
        self.interviews = interviews
        self.model = model
        self.artifacts = artifacts
        self.rag = rag
        self.audits = audits

    async def create(
        self,
        owner_id: UUID,
        interview_case_id: UUID,
        *,
        questions: tuple[str, ...],
        answers: tuple[str, ...],
        self_assessment: str,
        blockers: tuple[str, ...],
        outcome: str,
    ) -> CreateInterviewReviewResult:
        interview = await self._require_interview(owner_id, interview_case_id)
        review = InterviewReview.create(
            owner_id=owner_id,
            interview_case_id=interview.id,
            interview_case_version=interview.version,
            version=await self.reviews.next_version(interview.id),
            questions=questions,
            answers=answers,
            self_assessment=self_assessment,
            blockers=blockers,
            outcome=outcome,
        )
        suggestions = await self._generate(review)
        values = tuple(
            MemoryCandidate.propose(
                owner_id=owner_id,
                review_id=review.id,
                review_version=review.version,
                kind=MemoryCandidateKind(item.kind),
                text=item.text,
                reason=item.reason,
                confidence=item.confidence,
                unknown=item.unknown,
                suggested_action=item.suggested_action,
            )
            for item in suggestions
        )
        await self.reviews.add(review)
        for candidate in values:
            await self.candidates.add(candidate)
        await self.reviews.commit()
        return CreateInterviewReviewResult(review, values)

    async def latest(
        self, owner_id: UUID, interview_case_id: UUID
    ) -> tuple[InterviewReview, list[MemoryCandidate]]:
        await self._require_interview(owner_id, interview_case_id)
        review = await self.reviews.get_latest(interview_case_id)
        if review is None:
            raise ApplicationError(
                "Interview review not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return review, await self.candidates.list_for_review(review.id)

    async def versions(
        self, owner_id: UUID, interview_case_id: UUID
    ) -> list[tuple[InterviewReview, list[MemoryCandidate]]]:
        await self._require_interview(owner_id, interview_case_id)
        values = []
        for review in await self.reviews.list_versions(interview_case_id):
            values.append((review, await self.candidates.list_for_review(review.id)))
        return values

    async def confirm(self, owner_id: UUID, candidate_id: UUID) -> MemoryCandidate:
        candidate = await self._candidate(owner_id, candidate_id)
        if candidate.status.value != "proposed":
            raise ApplicationError(
                "Memory candidate cannot be confirmed",
                error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION,
            )
        content = (
            f"面试复盘记忆候选：{candidate.text}\n"
            f"原因：{candidate.reason}\n"
            f"建议动作：{candidate.suggested_action}"
        )
        artifact = None
        try:
            artifact = await self.artifacts.upload(
                UploadArtifactCommand(
                    owner_id=owner_id,
                    kind=ArtifactKind.SOURCE,
                    content_type="text/plain",
                    data=content.encode("utf-8"),
                    idempotency_key=f"memory-candidate-{candidate.id}",
                )
            )
            source = await self.artifacts.create_source(
                CreateSourceCommand(
                    owner_id=owner_id,
                    artifact_id=artifact.id,
                    source_kind=SourceKind.MANUAL,
                    acquisition_method="confirmed_interview_memory",
                    license_note="user_confirmed",
                    locator=f"memory-candidate:{candidate.id}",
                )
            )
            await self.rag.index_source(owner_id, source.id)
            updated = candidate.confirm(
                source_id=source.id,
                source_version=source.version,
                artifact_id=artifact.id,
                artifact_version=artifact.version,
            )
            await self.candidates.update(updated)
            await self._audit(updated)
            await self.candidates.commit()
            return updated
        except Exception as exc:
            if artifact is None:
                raise
            try:
                # Tombstoning the artifact removes its chunks from retrieval even
                # when Source creation or indexing has already committed.
                await self.artifacts.delete(owner_id, artifact.id)
            except Exception as cleanup_error:
                raise ExceptionGroup(
                    "Interview memory confirmation compensation failed",
                    [exc, cleanup_error],
                ) from exc
            raise

    async def reject(self, owner_id: UUID, candidate_id: UUID) -> MemoryCandidate:
        candidate = await self._candidate(owner_id, candidate_id)
        updated = candidate.reject()
        await self.candidates.update(updated)
        await self._audit(updated)
        await self.candidates.commit()
        return updated

    async def revoke(self, owner_id: UUID, candidate_id: UUID) -> MemoryCandidate:
        candidate = await self._candidate(owner_id, candidate_id)
        if candidate.status.value != "confirmed":
            raise ApplicationError(
                "Memory candidate cannot be revoked",
                error_code=ErrorCode.INVALID_CONFIRMATION_TRANSITION,
            )
        if candidate.artifact_id is not None:
            await self.artifacts.delete(owner_id, candidate.artifact_id)
        updated = candidate.revoke()
        await self.candidates.update(updated)
        await self._audit(updated)
        await self.candidates.commit()
        return updated

    async def _generate(self, review: InterviewReview) -> list[MemoryCandidateSuggestion]:
        if self.model is None:
            return []
        prompt = (
            "从用户提供的面试复盘生成待确认记忆候选。只返回候选，不保存事实，不输出思维链。\n"
            f"问题：{'；'.join(review.questions)}\n回答：{'；'.join(review.answers)}\n"
            f"自评：{review.self_assessment}\n卡点：{'；'.join(review.blockers) or 'unknown'}\n"
            f"结果：{review.outcome}"
        )
        try:
            result = await self.model.generate_structured(
                ModelRequest(
                    system_prompt=(
                        "Candidates must be reviewable suggestions. "
                        "Mark unknown when evidence is insufficient. "
                        "Never claim confirmation or alter a profile."
                    ),
                    user_input=prompt,
                    prompt_version=PROMPT_VERSION,
                    max_input_tokens=5_000,
                    max_output_tokens=2_000,
                    temperature=0,
                ),
                InterviewReviewAnalysis,
            )
        except ModelError:
            return []
        return result.candidates

    async def _require_interview(self, owner_id: UUID, interview_case_id: UUID) -> InterviewCase:
        value = await self.interviews.get_latest(interview_case_id)
        if value is None or value.owner_id != owner_id:
            raise ApplicationError("Interview not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return value

    async def _candidate(self, owner_id: UUID, candidate_id: UUID) -> MemoryCandidate:
        value = await self.candidates.get_by_id(candidate_id)
        if value is None or value.owner_id != owner_id:
            raise ApplicationError(
                "Memory candidate not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        return value

    async def _audit(self, value: MemoryCandidate) -> None:
        await self.audits.add(
            AuditEvent.create(
                actor_id=value.owner_id,
                action=AuditAction.UPDATE,
                target_type="memory_candidate",
                target_id=value.id,
                target_version=value.review_version,
                after_summary=(
                    f"kind={value.kind.value};status={value.status.value};"
                    f"review_version={value.review_version}"
                ),
            )
        )
