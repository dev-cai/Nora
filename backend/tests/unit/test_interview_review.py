from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.followup import InterviewReviewUseCases
from app.domain.base.exceptions import ApplicationError, DomainError, ErrorCode
from app.domain.followup import (
    InterviewCase,
    InterviewCaseStatus,
    InterviewMode,
    MemoryCandidateStatus,
)
from app.domain.knowledge import Artifact, ArtifactKind, SourceDocument, SourceKind
from app.infrastructure.model import FakeModelAdapter


class Reviews:
    def __init__(self) -> None:
        self.values = []

    async def next_version(self, _id):
        return len(self.values) + 1

    async def add(self, value):
        self.values.append(value)
        return value

    async def get_latest(self, interview_id):
        values = [item for item in self.values if item.interview_case_id == interview_id]
        return values[-1] if values else None

    async def list_versions(self, interview_id):
        return [item for item in self.values if item.interview_case_id == interview_id][::-1]

    async def commit(self):
        return None


class Candidates:
    def __init__(self) -> None:
        self.values = []

    async def add(self, value):
        self.values.append(value)
        return value

    async def update(self, value):
        self.values = [item if item.id != value.id else value for item in self.values]
        return value

    async def get_by_id(self, candidate_id):
        return next((item for item in self.values if item.id == candidate_id), None)

    async def list_for_review(self, review_id):
        return [item for item in self.values if item.review_id == review_id]

    async def commit(self):
        return None


class Interviews:
    def __init__(self, value):
        self.value = value

    async def get_latest(self, interview_id):
        return self.value if self.value.id == interview_id else None


class Artifacts:
    def __init__(self, owner):
        self.owner = owner
        self.deleted = []

    async def upload(self, command):
        artifact = Artifact.pending(
            owner_id=self.owner,
            kind=command.kind,
            content_type=command.content_type,
            size_bytes=len(command.data),
            sha256="a" * 64,
            idempotency_key=command.idempotency_key,
            now=datetime.now(timezone.utc),
        ).publish("memory-object")
        return artifact

    async def create_source(self, command):
        artifact = Artifact.pending(
            owner_id=self.owner,
            kind=ArtifactKind.SOURCE,
            content_type="text/plain",
            size_bytes=4,
            sha256="b" * 64,
            idempotency_key="source",
            now=datetime.now(timezone.utc),
        ).publish("source-object")
        return SourceDocument.create(
            artifact=artifact,
            source_kind=SourceKind.MANUAL,
            acquisition_method=command.acquisition_method,
            license_note=command.license_note,
        )

    async def delete(self, owner_id, artifact_id):
        assert owner_id == self.owner
        self.deleted.append(artifact_id)


class Rag:
    def __init__(self):
        self.indexed = []

    async def index_source(self, owner_id, source_id):
        self.indexed.append((owner_id, source_id))


class FailingRag(Rag):
    async def index_source(self, _owner_id, _source_id):
        raise RuntimeError("embedding unavailable")


class Audits:
    def __init__(self):
        self.values = []

    async def add(self, value):
        self.values.append(value)
        return value


def _fixture():
    owner = uuid4()
    interview = InterviewCase.create(
        owner_id=owner,
        actor_id=owner,
        application_record_id=uuid4(),
        starts_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        timezone_name="Asia/Shanghai",
        mode=InterviewMode.ONLINE,
        location=None,
        meeting_url="https://meet.example.com/x",
        round_number=1,
        note=None,
        status=InterviewCaseStatus.SCHEDULED,
        idempotency_key="review",
    )
    reviews, candidates, rag, audits = Reviews(), Candidates(), Rag(), Audits()
    use_cases = InterviewReviewUseCases(
        reviews,
        candidates,
        Interviews(interview),
        FakeModelAdapter(
            [
                {
                    "candidates": [
                        {
                            "kind": "skill_gap",
                            "text": "需要补充 PostgreSQL 索引知识",
                            "reason": "回答中出现查询计划卡点",
                            "confidence": 0.8,
                            "unknown": False,
                            "suggested_action": "复习索引和 EXPLAIN",
                        }
                    ],
                }
            ]
        ),
        Artifacts(owner),
        rag,
        audits,
    )
    return owner, interview, reviews, candidates, rag, use_cases


@pytest.mark.asyncio
async def test_review_generates_proposed_candidate_and_confirmed_memory_is_indexed() -> None:
    owner, interview, _reviews, candidates, rag, use_cases = _fixture()
    result = await use_cases.create(
        owner,
        interview.id,
        questions=("如何优化查询？",),
        answers=("我会看执行计划",),
        self_assessment="基本掌握",
        blockers=("没有写过索引迁移",),
        outcome="通过技术面",
    )
    candidate = result.candidates[0]
    assert candidate.status is MemoryCandidateStatus.PROPOSED
    confirmed = await use_cases.confirm(owner, candidate.id)
    assert confirmed.status is MemoryCandidateStatus.CONFIRMED
    assert confirmed.source_id is not None
    assert len(rag.indexed) == 1
    assert (await candidates.get_by_id(candidate.id)).status is MemoryCandidateStatus.CONFIRMED


@pytest.mark.asyncio
async def test_confirmation_failure_tombstones_created_artifact() -> None:
    owner, interview, _reviews, _candidates, _rag, _use_cases = _fixture()
    reviews, candidates, rag, audits = Reviews(), Candidates(), FailingRag(), Audits()
    artifacts = Artifacts(owner)
    use_cases = InterviewReviewUseCases(
        reviews,
        candidates,
        Interviews(interview),
        FakeModelAdapter(
            [
                {
                    "candidates": [
                        {
                            "kind": "knowledge_gap",
                            "text": "需要补充事务隔离知识",
                            "reason": "回答没有覆盖隔离级别",
                            "confidence": 0.7,
                            "unknown": False,
                            "suggested_action": "复习事务隔离",
                        }
                    ]
                }
            ]
        ),
        artifacts,
        rag,
        audits,
    )
    result = await use_cases.create(
        owner,
        interview.id,
        questions=("事务隔离级别？",),
        answers=("不确定",),
        self_assessment="不足",
        blockers=(),
        outcome="未通过",
    )

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await use_cases.confirm(owner, result.candidates[0].id)
    assert len(artifacts.deleted) == 1
    assert (
        await candidates.get_by_id(result.candidates[0].id)
    ).status is MemoryCandidateStatus.PROPOSED


@pytest.mark.asyncio
async def test_reject_revoke_and_owner_isolation_are_enforced() -> None:
    owner, interview, _reviews, candidates, _rag, use_cases = _fixture()
    result = await use_cases.create(
        owner,
        interview.id,
        questions=("问题",),
        answers=("回答",),
        self_assessment="一般",
        blockers=(),
        outcome="待定",
    )
    candidate = result.candidates[0]
    rejected = await use_cases.reject(owner, candidate.id)
    assert rejected.status is MemoryCandidateStatus.REJECTED
    with pytest.raises(ApplicationError) as exc:
        await use_cases.revoke(owner, candidate.id)
    assert exc.value.error_code is ErrorCode.INVALID_CONFIRMATION_TRANSITION

    owner, interview, _reviews, candidates, rag, use_cases = _fixture()
    result = await use_cases.create(
        owner,
        interview.id,
        questions=("问题",),
        answers=("回答",),
        self_assessment="一般",
        blockers=(),
        outcome="通过",
    )
    confirmed = await use_cases.confirm(owner, result.candidates[0].id)
    revoked = await use_cases.revoke(owner, confirmed.id)
    assert revoked.status is MemoryCandidateStatus.REVOKED
    assert revoked.source_id is None
    assert len(rag.indexed) == 1
    assert len(candidates.values) == 1
    with pytest.raises(ApplicationError) as exc:
        await use_cases.confirm(uuid4(), candidate.id)
    assert exc.value.error_code is ErrorCode.ENTITY_NOT_FOUND


def test_review_rejects_unaligned_questions_and_answers() -> None:
    owner = uuid4()
    with pytest.raises(DomainError):
        from app.domain.followup import InterviewReview

        InterviewReview.create(
            owner_id=owner,
            interview_case_id=uuid4(),
            interview_case_version=1,
            version=1,
            questions=("q1", "q2"),
            answers=("a1",),
            self_assessment="ok",
            blockers=(),
            outcome="x",
        )
