"""岗位快照应用用例单元测试。"""

from uuid import UUID, uuid4

import pytest

from nora.application.opportunity import (
    CreateJobPostingCommand,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
)
from nora.domain.base.exceptions import ApplicationError, InfrastructureError
from nora.domain.opportunity import JobPosting, JobSourceType
from nora.ports.opportunity import StoredIdempotentJobPosting


class FakeJobPostingRepository:
    """只保留用例可观察行为的内存 Repository。"""

    def __init__(self) -> None:
        self.postings: dict[UUID, JobPosting] = {}
        self.idempotency: dict[str, StoredIdempotentJobPosting] = {}
        self.commit_count = 0

    async def add(self, job_posting: JobPosting) -> JobPosting:
        self.postings[job_posting.id] = job_posting
        return job_posting

    async def add_idempotent(
        self,
        job_posting: JobPosting,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JobPosting:
        await self.add(job_posting)
        self.idempotency[idempotency_key] = StoredIdempotentJobPosting(
            job_posting=job_posting,
            request_fingerprint=request_fingerprint,
        )
        return job_posting

    async def get_by_id(self, job_posting_id: UUID) -> JobPosting | None:
        return self.postings.get(job_posting_id)

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> StoredIdempotentJobPosting | None:
        return self.idempotency.get(idempotency_key)

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[JobPosting]:
        return list(self.postings.values())[offset : offset + limit]

    async def commit(self) -> None:
        self.commit_count += 1


class RacingJobPostingRepository(FakeJobPostingRepository):
    """模拟首次查询后由并发事务占用幂等键。"""

    async def add_idempotent(
        self,
        job_posting: JobPosting,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JobPosting:
        self.idempotency[idempotency_key] = StoredIdempotentJobPosting(
            job_posting=job_posting,
            request_fingerprint=request_fingerprint,
        )
        raise InfrastructureError(
            "Concurrent request won",
            error_code="idempotency_key_taken",
        )


@pytest.mark.asyncio
async def test_create_replays_normalized_same_request() -> None:
    repository = FakeJobPostingRepository()
    use_case = CreateJobPostingUseCase(repository)
    owner_id = uuid4()

    created = await use_case.execute(
        CreateJobPostingCommand(
            owner_id=owner_id,
            idempotency_key=" import-1 ",
            jd_text="  Build APIs.\r\n",
        )
    )
    replayed = await use_case.execute(
        CreateJobPostingCommand(
            owner_id=owner_id,
            idempotency_key="import-1",
            jd_text="Build APIs.",
        )
    )

    assert created.replayed is False
    assert replayed.replayed is True
    assert replayed.job_posting.id == created.job_posting.id
    assert repository.commit_count == 1
    assert len(repository.postings) == 1


@pytest.mark.asyncio
async def test_create_rejects_same_key_with_different_content() -> None:
    repository = FakeJobPostingRepository()
    use_case = CreateJobPostingUseCase(repository)
    owner_id = uuid4()
    await use_case.execute(
        CreateJobPostingCommand(
            owner_id=owner_id,
            idempotency_key="import-1",
            jd_text="Build APIs.",
        )
    )

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(
            CreateJobPostingCommand(
                owner_id=owner_id,
                idempotency_key="import-1",
                jd_text="Build data pipelines.",
                source_type=JobSourceType.MANUAL,
            )
        )

    assert error.value.error_code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_create_recovers_result_after_concurrent_key_claim() -> None:
    repository = RacingJobPostingRepository()

    result = await CreateJobPostingUseCase(repository).execute(
        CreateJobPostingCommand(
            owner_id=uuid4(),
            idempotency_key="race-1",
            jd_text="Build APIs.",
        )
    )

    assert result.replayed is True
    assert result.job_posting.jd_text == "Build APIs."
    assert repository.commit_count == 0


@pytest.mark.asyncio
async def test_get_returns_owned_posting_and_hides_other_owner() -> None:
    repository = FakeJobPostingRepository()
    owner_id = uuid4()
    posting = JobPosting.create(owner_id=owner_id, jd_text="Build APIs.")
    await repository.add(posting)
    use_case = GetJobPostingUseCase(repository)

    assert (
        await use_case.execute(GetJobPostingQuery(owner_id=owner_id, job_posting_id=posting.id))
        == posting
    )

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(GetJobPostingQuery(owner_id=uuid4(), job_posting_id=posting.id))
    assert error.value.error_code == "entity_not_found"


@pytest.mark.asyncio
async def test_get_missing_posting_returns_stable_not_found() -> None:
    use_case = GetJobPostingUseCase(FakeJobPostingRepository())

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(GetJobPostingQuery(owner_id=uuid4(), job_posting_id=uuid4()))

    assert error.value.error_code == "entity_not_found"
