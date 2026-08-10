"""DecisionCase PostgreSQL 持久化、幂等与用户隔离测试。"""

from uuid import uuid4

import pytest
from app.application.decision import CreateDecisionCaseCommand, CreateDecisionCaseUseCase
from app.domain.base.exceptions import ApplicationError
from app.domain.career import CandidateProfile
from app.domain.opportunity import JobPosting, JobRequirementSnapshot
from app.infrastructure.database import (
    SqlAlchemyCandidateProfileRepository,
    SqlAlchemyDecisionCaseRepository,
    SqlAlchemyJobPostingRepository,
    SqlAlchemyJobRequirementSnapshotRepository,
    SqlAlchemyResumeVersionRepository,
    UserRecord,
    create_session_factory,
)
from sqlalchemy.ext.asyncio import AsyncEngine


def _profile_content(headline: str) -> dict[str, object]:
    return {
        "basic_information": {
            "headline": {
                "value": headline,
                "confirmation_status": "confirmed",
            }
        }
    }


def _requirement_content(skill: str) -> dict[str, object]:
    confirmed = {
        "confirmation_status": "confirmed",
        "source_type": "manual",
        "source_range": None,
    }
    return {
        "required_skills": {**confirmed, "value": [skill]},
        "minimum_experience_years": {**confirmed, "value": 3},
        "degree_requirement": {
            "value": None,
            "confirmation_status": "unknown",
            "source_type": "manual",
            "source_range": None,
        },
        "location_requirement": {**confirmed, "value": "北京"},
        "work_mode": {**confirmed, "value": "hybrid"},
    }


async def _seed_inputs(session, owner_id):
    posting_repository = SqlAlchemyJobPostingRepository(session, owner_id)
    posting = await posting_repository.add(
        JobPosting.create(owner_id=owner_id, jd_text="Python backend role")
    )
    await posting_repository.commit()

    requirement_repository = SqlAlchemyJobRequirementSnapshotRepository(session, owner_id)
    requirement = await requirement_repository.add(
        JobRequirementSnapshot.create(
            owner_id=owner_id,
            job_posting_id=posting.id,
            job_posting_version=posting.version,
            content=_requirement_content("Python"),
        )
    )
    await requirement_repository.commit()

    profile_repository = SqlAlchemyCandidateProfileRepository(session, owner_id)
    profile = await profile_repository.add(
        CandidateProfile.create(owner_id=owner_id, content=_profile_content("Engineer"))
    )
    await profile_repository.commit()

    resume_repository = SqlAlchemyResumeVersionRepository(session, owner_id)
    resume = await resume_repository.publish(profile, "Backend CV")
    await resume_repository.commit()
    return posting, requirement, profile, resume


def _command(
    owner_id,
    posting,
    requirement,
    profile,
    resume,
    rule_set_version: str = "rules-v1",
) -> CreateDecisionCaseCommand:
    return CreateDecisionCaseCommand(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        job_requirement_snapshot_id=requirement.id,
        job_requirement_snapshot_version=requirement.version,
        candidate_profile_id=profile.id,
        candidate_profile_version=profile.version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        rule_set_version=rule_set_version,
    )


@pytest.mark.asyncio
async def test_decision_case_round_trip_replay_and_historical_inputs(
    database_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(database_engine)
    owner = UserRecord(
        username=f"decision-owner-{uuid4()}",
        email=f"decision-owner-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add(owner)
        await session.commit()
        posting, requirement, profile, resume = await _seed_inputs(session, owner.id)
        repository = SqlAlchemyDecisionCaseRepository(session, owner.id)
        use_case = CreateDecisionCaseUseCase(
            repository,
            SqlAlchemyJobPostingRepository(session, owner.id),
            SqlAlchemyJobRequirementSnapshotRepository(session, owner.id),
            SqlAlchemyCandidateProfileRepository(session, owner.id),
            SqlAlchemyResumeVersionRepository(session, owner.id),
        )

        first = await use_case.execute(_command(owner.id, posting, requirement, profile, resume))
        replay = await use_case.execute(_command(owner.id, posting, requirement, profile, resume))
        assert first.replayed is False
        assert replay.replayed is True
        assert replay.decision_case.id == first.decision_case.id

        next_requirement = requirement.next_version(content=_requirement_content("Go"))
        await SqlAlchemyJobRequirementSnapshotRepository(session, owner.id).add(next_requirement)
        next_profile = profile.next_version(content=_profile_content("Principal Engineer"))
        await SqlAlchemyCandidateProfileRepository(session, owner.id).add(next_profile)
        await session.commit()

    async with factory() as session:
        restored = await SqlAlchemyDecisionCaseRepository(session, owner.id).get_by_id(
            first.decision_case.id
        )
        assert restored is not None
        assert restored.job_requirement_snapshot_version == 1
        assert restored.candidate_profile_version == 1
        assert restored.input_fingerprint == first.decision_case.input_fingerprint


@pytest.mark.asyncio
async def test_decision_case_persists_terminal_states(database_engine: AsyncEngine) -> None:
    factory = create_session_factory(database_engine)
    owner = UserRecord(
        username=f"decision-terminal-{uuid4()}",
        email=f"decision-terminal-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add(owner)
        await session.commit()
        posting, requirement, profile, resume = await _seed_inputs(session, owner.id)
        repository = SqlAlchemyDecisionCaseRepository(session, owner.id)
        use_case = CreateDecisionCaseUseCase(
            repository,
            SqlAlchemyJobPostingRepository(session, owner.id),
            SqlAlchemyJobRequirementSnapshotRepository(session, owner.id),
            SqlAlchemyCandidateProfileRepository(session, owner.id),
            SqlAlchemyResumeVersionRepository(session, owner.id),
        )

        completed = await use_case.execute(
            _command(owner.id, posting, requirement, profile, resume)
        )
        completed_case = await repository.update(completed.decision_case.complete())
        assert completed_case.status.value == "completed"
        assert completed_case.completed_at is not None
        await repository.commit()

        failed = await use_case.execute(
            _command(owner.id, posting, requirement, profile, resume, rule_set_version="rules-v2")
        )
        failed_case = await repository.update(
            failed.decision_case.fail(
                failure_code="rule_error",
                failure_message="Rule execution failed",
            )
        )
        assert failed_case.status.value == "failed"
        assert failed_case.failure_code == "rule_error"
        assert failed_case.failure_message == "Rule execution failed"
        await repository.commit()

    async with factory() as session:
        restored_completed = await SqlAlchemyDecisionCaseRepository(session, owner.id).get_by_id(
            completed.decision_case.id
        )
        restored_failed = await SqlAlchemyDecisionCaseRepository(session, owner.id).get_by_id(
            failed.decision_case.id
        )
        assert restored_completed is not None
        assert restored_completed.status.value == "completed"
        assert restored_failed is not None
        assert restored_failed.status.value == "failed"
        assert restored_failed.failure_code == "rule_error"


@pytest.mark.asyncio
async def test_decision_case_rejects_foreign_user_inputs(database_engine: AsyncEngine) -> None:
    factory = create_session_factory(database_engine)
    owner_a = UserRecord(
        username=f"decision-owner-a-{uuid4()}",
        email=f"decision-owner-a-{uuid4()}@example.com",
        password_hash="hash",
    )
    owner_b = UserRecord(
        username=f"decision-owner-b-{uuid4()}",
        email=f"decision-owner-b-{uuid4()}@example.com",
        password_hash="hash",
    )
    async with factory() as session:
        session.add_all([owner_a, owner_b])
        await session.commit()
        posting, requirement, profile, resume = await _seed_inputs(session, owner_b.id)
        use_case = CreateDecisionCaseUseCase(
            SqlAlchemyDecisionCaseRepository(session, owner_a.id),
            SqlAlchemyJobPostingRepository(session, owner_a.id),
            SqlAlchemyJobRequirementSnapshotRepository(session, owner_a.id),
            SqlAlchemyCandidateProfileRepository(session, owner_a.id),
            SqlAlchemyResumeVersionRepository(session, owner_a.id),
        )

        with pytest.raises(ApplicationError) as error:
            await use_case.execute(_command(owner_a.id, posting, requirement, profile, resume))
        assert error.value.error_code == "entity_not_found"
