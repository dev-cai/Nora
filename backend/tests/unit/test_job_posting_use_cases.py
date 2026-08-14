"""岗位快照应用用例单元测试。"""

import json
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from app.application.opportunity import (
    CreateJobPostingCommand,
    CreateJobPostingUseCase,
    GetJobPostingQuery,
    GetJobPostingUseCase,
    ListJobPostingsQuery,
    ListJobPostingsUseCase,
)
from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.governance import AuditEvent
from app.domain.opportunity import JobPosting, JobSourceType
from app.ports.opportunity import StoredIdempotentJobPosting


class FakeJobPostingRepository:
    """只保留用例可观察行为的内存 Repository。"""

    def __init__(self) -> None:
        self.postings: dict[UUID, JobPosting] = {}
        self.idempotency: dict[str, StoredIdempotentJobPosting] = {}

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

    async def count(self) -> int:
        return len(self.postings)


class FakeAuditEventRepository:
    """记录用例追加的审计事件。"""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event


class FailingAuditEventRepository:
    async def add(self, event: AuditEvent) -> AuditEvent:
        raise RuntimeError("audit failed")


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RacingJobPostingRepository(FakeJobPostingRepository):
    """模拟首次查询后由并发事务占用幂等键。"""

    def __init__(self, transaction: FakeTransaction) -> None:
        super().__init__()
        self.transaction = transaction
        self.claimed = False

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> StoredIdempotentJobPosting | None:
        if self.claimed and self.transaction.rollbacks == 0:
            raise AssertionError("recovery query ran before rollback")
        return await super().get_by_idempotency_key(idempotency_key)

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
        self.claimed = True
        raise InfrastructureError(
            "Concurrent request won",
            error_code="idempotency_key_taken",
        )


@pytest.mark.asyncio
async def test_create_replays_normalized_same_request() -> None:
    repository = FakeJobPostingRepository()
    audit_repository = FakeAuditEventRepository()
    transaction = FakeTransaction()
    use_case = CreateJobPostingUseCase(repository, audit_repository, transaction)
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
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    assert len(repository.postings) == 1
    assert len(audit_repository.events) == 1
    event = audit_repository.events[0]
    assert event.actor_id == owner_id
    assert event.target_id == created.job_posting.id
    assert event.target_type == "job_posting"
    assert event.target_version == created.job_posting.version == 1
    assert event.idempotency_key == "import-1"
    assert json.loads(event.after_summary or "{}") == {
        "source_type": "manual",
        "status": "active",
    }
    assert "Build APIs." not in (event.after_summary or "")


@pytest.mark.asyncio
async def test_create_rejects_same_key_with_different_content() -> None:
    repository = FakeJobPostingRepository()
    audit_repository = FakeAuditEventRepository()
    use_case = CreateJobPostingUseCase(repository, audit_repository, FakeTransaction())
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
    assert len(audit_repository.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed_fields",
    [
        {"jd_text": "Build data pipelines."},
        {"job_title": "Platform Engineer"},
        {"company_name": "Another Corp"},
        {"location": "Beijing"},
        {"source_type": JobSourceType.MANUAL},
        {"source_url": "https://jobs.example.com/roles/456"},
    ],
    ids=["jd-text", "job-title", "company-name", "location", "source-type", "source-url"],
)
async def test_create_fingerprint_covers_every_public_field(
    changed_fields: dict[str, object],
) -> None:
    repository = FakeJobPostingRepository()
    use_case = CreateJobPostingUseCase(repository, FakeAuditEventRepository(), FakeTransaction())
    owner_id = uuid4()
    command_values = {
        "jd_text": "Build APIs.",
        "job_title": "Backend Engineer",
        "company_name": "Example Corp",
        "location": "Shanghai",
        "source_type": JobSourceType.URL,
        "source_url": "https://jobs.example.com/roles/123",
    }
    await use_case.execute(
        CreateJobPostingCommand(
            owner_id=owner_id,
            idempotency_key="import-metadata",
            **command_values,
        )
    )
    expected_fingerprint = sha256(
        json.dumps(
            {
                "company_name": "Example Corp",
                "jd_text": "Build APIs.",
                "job_title": "Backend Engineer",
                "location": "Shanghai",
                "source_type": "url",
                "source_url": "https://jobs.example.com/roles/123",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert repository.idempotency["import-metadata"].request_fingerprint == expected_fingerprint

    changed_command_values = {**command_values, **changed_fields}

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(
            CreateJobPostingCommand(
                owner_id=owner_id,
                idempotency_key="import-metadata",
                **changed_command_values,
            )
        )

    assert error.value.error_code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_create_recovers_result_after_concurrent_key_claim() -> None:
    transaction = FakeTransaction()
    repository = RacingJobPostingRepository(transaction)
    audit_repository = FakeAuditEventRepository()

    result = await CreateJobPostingUseCase(repository, audit_repository, transaction).execute(
        CreateJobPostingCommand(
            owner_id=uuid4(),
            idempotency_key="race-1",
            jd_text="Build APIs.",
        )
    )

    assert result.replayed is True
    assert result.job_posting.jd_text == "Build APIs."
    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert audit_repository.events == []


@pytest.mark.asyncio
async def test_create_rolls_back_when_audit_write_fails() -> None:
    transaction = FakeTransaction()

    with pytest.raises(RuntimeError, match="audit failed"):
        await CreateJobPostingUseCase(
            FakeJobPostingRepository(),
            FailingAuditEventRepository(),
            transaction,
        ).execute(
            CreateJobPostingCommand(
                owner_id=uuid4(),
                idempotency_key="audit-failure",
                jd_text="Build APIs.",
            )
        )

    assert transaction.commits == 0
    assert transaction.rollbacks == 1


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


@pytest.mark.asyncio
async def test_list_returns_requested_page_and_total() -> None:
    repository = FakeJobPostingRepository()
    owner_id = uuid4()
    postings = [JobPosting.create(owner_id=owner_id, jd_text=f"Role {index}") for index in range(3)]
    for posting in postings:
        await repository.add(posting)

    result = await ListJobPostingsUseCase(repository).execute(
        ListJobPostingsQuery(owner_id=owner_id, page=2, page_size=2)
    )

    assert result.items == (postings[2],)
    assert result.page == 2
    assert result.page_size == 2
    assert result.total == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("page", "page_size"), [(0, 20), (1, 0), (1, 101)])
async def test_list_rejects_invalid_pagination(page: int, page_size: int) -> None:
    with pytest.raises(ApplicationError) as error:
        await ListJobPostingsUseCase(FakeJobPostingRepository()).execute(
            ListJobPostingsQuery(owner_id=uuid4(), page=page, page_size=page_size)
        )

    assert error.value.error_code == "invalid_pagination"
