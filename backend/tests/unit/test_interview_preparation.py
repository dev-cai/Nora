"""Interview preparation generation, fallback, version and owner tests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.application.followup.interview_preparation import InterviewPreparationUseCases
from app.application.knowledge import KnowledgeAnswer, RetrievedEvidence
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.domain.followup import InterviewCase, InterviewCaseStatus, InterviewMode


class MemoryPreparations:
    def __init__(self) -> None:
        self.items = []

    async def next_version(self, interview_case_id: UUID) -> int:
        return len([item for item in self.items if item.interview_case_id == interview_case_id]) + 1

    async def add(self, preparation):
        self.items.append(preparation)
        return preparation

    async def get_latest(self, interview_case_id: UUID):
        values = [item for item in self.items if item.interview_case_id == interview_case_id]
        return values[-1] if values else None

    async def get_version(self, interview_case_id: UUID, version: int):
        return next(
            (
                item
                for item in self.items
                if item.interview_case_id == interview_case_id and item.version == version
            ),
            None,
        )

    async def list_versions(self, interview_case_id: UUID):
        values = [item for item in self.items if item.interview_case_id == interview_case_id]
        return sorted(values, key=lambda item: item.version, reverse=True)

    async def commit(self) -> None:
        return None


class SingleRepository:
    def __init__(self, value) -> None:
        self.value = value

    async def get_latest(self, value_id: UUID):
        return self.value if self.value.id == value_id else None

    async def get_by_id(self, value_id: UUID):
        return self.value if self.value.id == value_id else None


class Reports:
    def __init__(self, report) -> None:
        self.report = report

    async def list_for_case(self, case_id: UUID):
        return [self.report] if self.report.decision_case_id == case_id else []


class ResumeRepository:
    def __init__(self, value) -> None:
        self.value = value

    async def get_by_identity(self, resume_id: UUID, version: int):
        if self.value.id == resume_id and self.value.version == version:
            return self.value
        return None


class JobFitRepository:
    async def get_for_report(self, report_id: UUID):
        return None


class Rag:
    def __init__(self, answer: KnowledgeAnswer) -> None:
        self.answer = answer

    async def ask(self, owner_id: UUID, query: str, *, limit: int):
        assert owner_id and query and limit == 5
        return self.answer


def fixture(answer: KnowledgeAnswer):
    owner_id = uuid4()
    application_id = uuid4()
    decision_case_id = uuid4()
    resume_id = uuid4()
    job_id = uuid4()
    interview = InterviewCase.create(
        owner_id=owner_id,
        actor_id=owner_id,
        application_record_id=application_id,
        starts_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        timezone_name="Asia/Shanghai",
        mode=InterviewMode.ONLINE,
        location=None,
        meeting_url="https://meet.example.com/round-1",
        round_number=1,
        note=None,
        status=InterviewCaseStatus.SCHEDULED,
        idempotency_key="prepare-test",
    )
    application = SimpleNamespace(
        id=application_id, owner_id=owner_id, decision_case_id=decision_case_id
    )
    decision_case = SimpleNamespace(
        id=decision_case_id,
        owner_id=owner_id,
        resume_version_id=resume_id,
        resume_version=1,
        job_posting_id=job_id,
        job_posting_version=1,
    )
    resume = SimpleNamespace(id=resume_id, owner_id=owner_id, version=1, title="后端简历")
    job = SimpleNamespace(
        id=job_id,
        owner_id=owner_id,
        version=1,
        job_title="后端工程师",
        company_name="示例公司",
        text_summary="Python 与检索",
    )
    report = SimpleNamespace(
        id=uuid4(), owner_id=owner_id, decision_case_id=decision_case_id, version=1
    )
    preparations = MemoryPreparations()
    use_cases = InterviewPreparationUseCases(
        preparations,
        SingleRepository(interview),
        SingleRepository(application),
        SingleRepository(decision_case),
        Reports(report),
        ResumeRepository(resume),
        SingleRepository(job),
        JobFitRepository(),
        Rag(answer),
    )
    return owner_id, interview, preparations, use_cases


@pytest.mark.asyncio
async def test_generation_keeps_retrieval_citations_and_appends_versions() -> None:
    evidence = RetrievedEvidence(uuid4(), uuid4(), 2, "page:3", "Python 检索项目", 0.91)
    owner_id, interview, preparations, use_cases = fixture(
        KnowledgeAnswer("query", "重点追问检索项目的取舍", "grounded", (evidence,))
    )

    first = await use_cases.generate(owner_id, interview.id)
    second = await use_cases.generate(owner_id, interview.id)

    assert first.preparation.version == 1
    assert second.preparation.version == 2
    assert second.preparation.topics[0].citation_ids == (evidence.chunk_id,)
    assert second.preparation.topics[0].status == "grounded"
    assert [item.version for item in await preparations.list_versions(interview.id)] == [2, 1]
    assert (await use_cases.get_version(owner_id, interview.id, 1)).id == first.preparation.id


@pytest.mark.asyncio
async def test_unknown_fallback_is_explicit_and_owner_isolated() -> None:
    owner_id, interview, _preparations, use_cases = fixture(
        KnowledgeAnswer("query", "unknown", "unknown", ())
    )
    value = (await use_cases.generate(owner_id, interview.id)).preparation

    assert all(topic.status == "unknown" for topic in value.topics)
    assert all(topic.reason.startswith("unknown") for topic in value.topics)
    assert value.citations == ()
    with pytest.raises(ApplicationError) as exc:
        await use_cases.get_latest(uuid4(), interview.id)
    assert exc.value.error_code is ErrorCode.ENTITY_NOT_FOUND
