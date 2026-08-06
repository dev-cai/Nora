"""岗位要求快照 Repository 版本追加与用户隔离测试。"""

from uuid import uuid4

import pytest
from app.domain.base.exceptions import InfrastructureError
from app.domain.opportunity import JobPosting, JobRequirementSnapshot
from app.infrastructure.database import (
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
    UserRecord,
    create_session_factory,
)
from sqlalchemy.ext.asyncio import AsyncEngine


def _content(skills: list[str] | None = None) -> dict[str, object]:
    return {
        "required_skills": {
            "value": skills or [],
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "minimum_experience_years": {
            "value": 3,
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "degree_requirement": {
            "value": "本科",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "location_requirement": {
            "value": "北京",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "work_mode": {
            "value": "hybrid",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
    }


async def _create_posting(session, owner_id) -> str:
    repository = SqlAlchemyJobPostingRepository(session, owner_id)
    posting = JobPosting.create(
        owner_id=owner_id,
        jd_text="Senior backend engineer with Python and FastAPI.",
        job_title="Backend Engineer",
        company_name="Example Corp",
    )
    stored = await repository.add(posting)
    await repository.commit()
    return stored.id


@pytest.mark.asyncio
async def test_requirement_repository_round_trip_and_user_scope(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)
    owner_a = UserRecord(
        username=f"req-owner-a-{uuid4()}",
        email=f"req-owner-a-{uuid4()}@example.com",
        password_hash="hash",
    )
    owner_b = UserRecord(
        username=f"req-owner-b-{uuid4()}",
        email=f"req-owner-b-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add_all([owner_a, owner_b])
        await session.commit()

        posting_id = await _create_posting(session, owner_a.id)
        repository_a = SqlAlchemyJobRequirementSnapshotRepository(session, owner_a.id)
        first = JobRequirementSnapshot.create(
            owner_id=owner_a.id,
            job_posting_id=posting_id,
            job_posting_version=1,
            content=_content(skills=["Python"]),
        )
        stored = await repository_a.add(first)
        await repository_a.commit()

        second = first.next_version(content=_content(skills=["Python", "SQL"]))
        await repository_a.add(second)
        await repository_a.commit()

    async with factory() as session:
        repository_a = SqlAlchemyJobRequirementSnapshotRepository(session, owner_a.id)
        repository_b = SqlAlchemyJobRequirementSnapshotRepository(session, owner_b.id)

        latest = await repository_a.get_latest(posting_id)
        assert latest is not None
        assert latest.version == 2
        assert latest.content["required_skills"]["value"] == ["Python", "SQL"]

        first_version = await repository_a.get_version(posting_id, 1)
        assert first_version is not None
        assert first_version.version == 1
        assert first_version.content_hash != latest.content_hash

        restored_by_id = await repository_a.get_by_id(stored.id)
        assert restored_by_id is not None
        assert restored_by_id.version == 2

        assert [item.version for item in await repository_a.list(posting_id)] == [2, 1]
        assert await repository_a.count(posting_id) == 2

        assert await repository_b.get_latest(posting_id) is None
        assert await repository_b.list(posting_id) == []
        assert await repository_b.count(posting_id) == 0
        with pytest.raises(InfrastructureError, match="outside user scope"):
            await repository_b.add(second)


@pytest.mark.asyncio
async def test_requirement_repository_rejects_version_conflicts(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)
    owner = UserRecord(
        username=f"req-owner-c-{uuid4()}",
        email=f"req-owner-c-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add(owner)
        await session.commit()

        posting_id = await _create_posting(session, owner.id)
        repository = SqlAlchemyJobRequirementSnapshotRepository(session, owner.id)
        first = JobRequirementSnapshot.create(
            owner_id=owner.id,
            job_posting_id=posting_id,
            job_posting_version=1,
            content=_content(skills=["Python"]),
        )
        await repository.add(first)
        await repository.commit()

        duplicate = JobRequirementSnapshot.create(
            owner_id=owner.id,
            job_posting_id=posting_id,
            job_posting_version=1,
            content=_content(skills=["Go"]),
        )
        with pytest.raises(InfrastructureError) as error:
            await repository.add(duplicate)
        assert error.value.error_code == "job_requirement_version_conflict"

        skipping = JobRequirementSnapshot.restore(
            snapshot_id=first.id,
            owner_id=first.owner_id,
            version=3,
            job_posting_id=first.job_posting_id,
            job_posting_version=first.job_posting_version,
            content=_content(skills=["Go"]),
            created_at=first.created_at,
            updated_at=first.updated_at,
        )
        with pytest.raises(InfrastructureError) as error:
            await repository.add(skipping)
        assert error.value.error_code == "job_requirement_version_conflict"
