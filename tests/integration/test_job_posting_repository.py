"""岗位快照 Repository 集成测试。"""

import os
from uuid import uuid4

import pytest

from nora.domain.base.exceptions import InfrastructureError
from nora.domain.opportunity import JobPosting, JobSourceType
from nora.infrastructure.config import Settings
from nora.infrastructure.database import (
    Base,
    SqlAlchemyJobPostingRepository,
    UserRecord,
    create_database_engine,
    create_session_factory,
)


@pytest.mark.asyncio
async def test_job_posting_repository_round_trip_and_user_scope() -> None:
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = create_database_engine(Settings(database_url=database_url), database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    owner_a = UserRecord(
        username=f"posting-owner-a-{uuid4()}",
        email=f"posting-owner-a-{uuid4()}@example.com",
        password_hash="hash",
    )
    owner_b = UserRecord(
        username=f"posting-owner-b-{uuid4()}",
        email=f"posting-owner-b-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add_all([owner_a, owner_b])
        await session.commit()

        repository_a = SqlAlchemyJobPostingRepository(session, owner_a.id)
        posting = JobPosting.create(
            owner_id=owner_a.id,
            jd_text="Build and maintain Python services.",
            job_title="Backend Engineer",
            company_name="Example Corp",
            source_type=JobSourceType.URL,
            source_url="https://jobs.example.com/backend",
        )
        stored = await repository_a.add(posting)
        await repository_a.commit()
        posting_id = stored.id

        repository_b = SqlAlchemyJobPostingRepository(session, owner_b.id)
        with pytest.raises(InfrastructureError, match="outside user scope"):
            await repository_b.add(posting)

    async with factory() as session:
        repository_a = SqlAlchemyJobPostingRepository(session, owner_a.id)
        repository_b = SqlAlchemyJobPostingRepository(session, owner_b.id)

        restored = await repository_a.get_by_id(posting_id)
        assert restored is not None
        assert restored.id == posting.id
        assert restored.owner_id == owner_a.id
        assert restored.jd_text == posting.jd_text
        assert restored.job_title == "Backend Engineer"
        assert restored.source_type is JobSourceType.URL
        assert restored.created_at == posting.created_at
        assert [item.id for item in await repository_a.list()] == [posting_id]

        assert await repository_b.get_by_id(posting_id) is None
        assert await repository_b.list() == []

    await engine.dispose()
