"""JobRequirementSnapshot 领域与应用用例测试。"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.opportunity import (
    GetJobRequirementSnapshotQuery,
    GetJobRequirementSnapshotUseCase,
    ListJobRequirementSnapshotsQuery,
    ListJobRequirementSnapshotsUseCase,
    SaveJobRequirementSnapshotCommand,
    SaveJobRequirementSnapshotUseCase,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.opportunity import JobPosting, JobRequirementSnapshot


def _content(
    *,
    skills: list[str] | None = None,
    status: str = "unconfirmed",
    source: str = "manual",
    work_mode: str = "hybrid",
) -> dict[str, object]:
    return {
        "required_skills": {
            "value": skills or [],
            "confirmation_status": status,
            "source_type": source,
            "source_range": None,
        },
        "minimum_experience_years": {
            "value": 3,
            "confirmation_status": status,
            "source_type": source,
            "source_range": None,
        },
        "degree_requirement": {
            "value": "本科",
            "confirmation_status": status,
            "source_type": source,
            "source_range": None,
        },
        "location_requirement": {
            "value": "北京",
            "confirmation_status": status,
            "source_type": source,
            "source_range": None,
        },
        "work_mode": {
            "value": work_mode,
            "confirmation_status": status,
            "source_type": source,
            "source_range": None,
        },
    }


def _posting(owner_id) -> JobPosting:
    return JobPosting.create(owner_id=owner_id, jd_text="Senior Backend Engineer JD")


class MemoryPostingRepository:
    def __init__(self, posting: JobPosting | None) -> None:
        self.posting = posting

    async def get_by_id(self, job_posting_id):
        if self.posting is not None and self.posting.id == job_posting_id:
            return self.posting
        return None

    async def add(self, posting: JobPosting) -> JobPosting:
        return posting

    async def commit(self) -> None:
        return None


class MemoryRequirementRepository:
    def __init__(self) -> None:
        self.items: list[JobRequirementSnapshot] = []

    async def add(self, snapshot: JobRequirementSnapshot) -> JobRequirementSnapshot:
        self.items.append(snapshot)
        return snapshot

    async def get_by_id(self, snapshot_id):
        return next((item for item in self.items if item.id == snapshot_id), None)

    async def get_latest(self, job_posting_id):
        versions = [item for item in self.items if item.job_posting_id == job_posting_id]
        return max(versions, key=lambda item: item.version, default=None)

    async def get_version(self, job_posting_id, version):
        return next(
            (
                item
                for item in self.items
                if item.job_posting_id == job_posting_id and item.version == version
            ),
            None,
        )

    async def list(self, job_posting_id, *, offset: int = 0, limit: int = 100):
        versions = sorted(
            [item for item in self.items if item.job_posting_id == job_posting_id],
            key=lambda item: item.version,
            reverse=True,
        )
        return versions[offset : offset + limit]

    async def count(self, job_posting_id) -> int:
        return len([item for item in self.items if item.job_posting_id == job_posting_id])

    async def commit(self) -> None:
        return None


def test_snapshot_create_normalizes_content_and_versions() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    content = _content(
        skills=[" Python ", "FastAPI"], status="confirmed", source="text_range", work_mode="remote"
    )
    content["minimum_experience_years"] = {
        "value": 3,
        "confirmation_status": "confirmed",
        "source_type": "text_range",
        "source_range": "[120,130]",
    }

    snapshot = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        content=content,
        now=datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
    )

    assert snapshot.version == 1
    assert snapshot.job_posting_id == posting.id
    assert snapshot.job_posting_version == 1
    assert snapshot.content["required_skills"]["value"] == ["Python", "FastAPI"]
    assert snapshot.content["work_mode"]["value"] == "remote"
    assert snapshot.content["minimum_experience_years"]["source_range"] == "[120,130]"
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, "version", 2)


def test_snapshot_next_version_preserves_posting_and_created_at() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    created = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=1,
        content=_content(),
        now=datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
    )

    next_snapshot = created.next_version(
        content=_content(skills=["Python", "SQL"]),
        now=datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc),
    )

    assert next_snapshot.id == created.id
    assert next_snapshot.version == 2
    assert next_snapshot.job_posting_id == created.job_posting_id
    assert next_snapshot.job_posting_version == created.job_posting_version
    assert next_snapshot.created_at == created.created_at
    assert next_snapshot.updated_at == datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)
    assert next_snapshot.content["required_skills"]["value"] == ["Python", "SQL"]


def test_snapshot_rejects_unknown_field_with_value() -> None:
    content = _content(status="unknown")
    content["degree_requirement"] = {
        "value": "本科",
        "confirmation_status": "unknown",
        "source_type": "manual",
        "source_range": None,
    }
    with pytest.raises(DomainError) as error:
        JobRequirementSnapshot.create(
            owner_id=uuid4(), job_posting_id=uuid4(), job_posting_version=1, content=content
        )
    assert error.value.error_code == "invalid_requirement_field"


def test_snapshot_rejects_invalid_work_mode() -> None:
    content = _content(work_mode="invalid")
    with pytest.raises(DomainError) as error:
        JobRequirementSnapshot.create(
            owner_id=uuid4(), job_posting_id=uuid4(), job_posting_version=1, content=content
        )
    assert error.value.error_code == "invalid_requirement_field"


def test_snapshot_rejects_missing_field() -> None:
    content = _content()
    del content["work_mode"]
    with pytest.raises(DomainError) as error:
        JobRequirementSnapshot.create(
            owner_id=uuid4(), job_posting_id=uuid4(), job_posting_version=1, content=content
        )
    assert error.value.error_code == "invalid_requirement"
    assert "work_mode" in error.value.message


def test_snapshot_content_hash_is_stable_and_distinct() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    first = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=1,
        content=_content(skills=["Python"]),
    )
    same = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=1,
        content=_content(skills=["Python"]),
    )
    different = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=1,
        content=_content(skills=["Go"]),
    )
    assert first.content_hash == same.content_hash
    assert first.content_hash != different.content_hash


def test_snapshot_confirmed_requirements_returns_only_confirmed() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    content = _content(status="confirmed")
    content["degree_requirement"] = {
        "value": "本科",
        "confirmation_status": "unconfirmed",
        "source_type": "manual",
        "source_range": None,
    }
    snapshot = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=1,
        content=content,
    )
    confirmed = snapshot.confirmed_requirements()
    assert confirmed["required_skills"] == []
    assert confirmed["minimum_experience_years"] == 3
    assert "degree_requirement" not in confirmed


@pytest.mark.asyncio
async def test_save_creates_first_then_next_version_and_replays() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    postings = MemoryPostingRepository(posting)
    requirements = MemoryRequirementRepository()
    use_case = SaveJobRequirementSnapshotUseCase(requirements, postings)

    first = await use_case.execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=1,
            content=_content(skills=["Python"]),
        )
    )
    assert first.replayed is False
    assert first.snapshot.version == 1

    replay = await use_case.execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=1,
            content=_content(skills=["Python"]),
        )
    )
    assert replay.replayed is True
    assert replay.snapshot.version == 1

    changed = await use_case.execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=1,
            content=_content(skills=["Python", "SQL"]),
        )
    )
    assert changed.replayed is False
    assert changed.snapshot.version == 2
    assert changed.snapshot.id == first.snapshot.id


@pytest.mark.asyncio
async def test_save_rejects_unknown_or_foreign_posting() -> None:
    owner_id = uuid4()
    requirements = MemoryRequirementRepository()
    with pytest.raises(ApplicationError) as error:
        await SaveJobRequirementSnapshotUseCase(
            requirements, MemoryPostingRepository(None)
        ).execute(
            SaveJobRequirementSnapshotCommand(
                owner_id=owner_id,
                job_posting_id=uuid4(),
                job_posting_version=1,
                content=_content(),
            )
        )
    assert error.value.error_code == "entity_not_found"


@pytest.mark.asyncio
async def test_get_latest_version_and_list() -> None:
    owner_id = uuid4()
    posting = _posting(owner_id)
    requirements = MemoryRequirementRepository()
    use_case = SaveJobRequirementSnapshotUseCase(requirements, MemoryPostingRepository(posting))
    await use_case.execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=1,
            content=_content(skills=["Python"]),
        )
    )
    await use_case.execute(
        SaveJobRequirementSnapshotCommand(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=1,
            content=_content(skills=["Python", "SQL"]),
        )
    )

    latest = await GetJobRequirementSnapshotUseCase(requirements).execute(
        GetJobRequirementSnapshotQuery(owner_id=owner_id, job_posting_id=posting.id)
    )
    first = await GetJobRequirementSnapshotUseCase(requirements).execute(
        GetJobRequirementSnapshotQuery(owner_id=owner_id, job_posting_id=posting.id, version=1)
    )
    listed = await ListJobRequirementSnapshotsUseCase(requirements).execute(
        ListJobRequirementSnapshotsQuery(owner_id=owner_id, job_posting_id=posting.id)
    )

    assert latest.version == 2
    assert first.version == 1
    assert [item.version for item in listed.items] == [2, 1]
    assert listed.total == 2


@pytest.mark.asyncio
async def test_get_hides_missing_or_foreign_snapshot() -> None:
    owner_id = uuid4()
    requirements = MemoryRequirementRepository()
    with pytest.raises(ApplicationError) as error:
        await GetJobRequirementSnapshotUseCase(requirements).execute(
            GetJobRequirementSnapshotQuery(owner_id=owner_id, job_posting_id=uuid4())
        )
    assert error.value.error_code == "entity_not_found"
