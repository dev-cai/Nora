"""DecisionCase 领域契约与应用输入不变量测试。"""

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.decision import (
    CreateDecisionCaseCommand,
    CreateDecisionCaseUseCase,
    GetDecisionCaseQuery,
    GetDecisionCaseUseCase,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import CandidateProfile, ResumeVersion
from app.domain.decision import DecisionCase, DecisionCaseStatus
from app.domain.opportunity import JobPosting, JobRequirementSnapshot


def _requirement_content() -> dict[str, object]:
    return {
        "required_skills": {
            "value": ["Python"],
            "confirmation_status": "confirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "minimum_experience_years": {
            "value": 3,
            "confirmation_status": "confirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "degree_requirement": {
            "value": None,
            "confirmation_status": "unknown",
            "source_type": "manual",
            "source_range": None,
        },
        "location_requirement": {
            "value": "北京",
            "confirmation_status": "confirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "work_mode": {
            "value": "hybrid",
            "confirmation_status": "confirmed",
            "source_type": "manual",
            "source_range": None,
        },
    }


def _profile_content() -> dict[str, object]:
    return {
        "basic_information": {
            "headline": {
                "value": "Backend Engineer",
                "confirmation_status": "confirmed",
            }
        }
    }


def _case_kwargs() -> dict[str, object]:
    return {
        "owner_id": uuid4(),
        "job_posting_id": uuid4(),
        "job_posting_version": 1,
        "job_requirement_snapshot_id": uuid4(),
        "job_requirement_snapshot_version": 2,
        "candidate_profile_id": uuid4(),
        "candidate_profile_version": 3,
        "resume_version_id": uuid4(),
        "resume_version": 4,
        "rule_set_version": "rules-v1",
    }


def test_decision_case_normalizes_rule_set_and_has_deterministic_fingerprint() -> None:
    values = _case_kwargs()
    first = DecisionCase.create(**values, now=datetime(2026, 8, 10, tzinfo=timezone.utc))
    second = DecisionCase.create(
        **{**values, "rule_set_version": "  rules-v1  "},
        now=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )

    assert first.id != second.id
    assert first.input_fingerprint == second.input_fingerprint
    assert first.rule_set_version == "rules-v1"
    assert first.status is DecisionCaseStatus.CREATED
    assert first.completed_at is None


def test_decision_case_fingerprint_changes_with_an_input_version() -> None:
    values = _case_kwargs()
    first = DecisionCase.create(**values)
    second = DecisionCase.create(**{**values, "resume_version": 5})

    assert first.input_fingerprint != second.input_fingerprint


def test_decision_case_terminal_states_are_immutable_transitions() -> None:
    case = DecisionCase.create(**_case_kwargs())
    completed = case.complete(now=datetime(2026, 8, 10, tzinfo=timezone.utc))
    failed = case.fail(
        failure_code="rule_error",
        failure_message="Rule execution failed",
        now=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert completed.status is DecisionCaseStatus.COMPLETED
    assert failed.status is DecisionCaseStatus.FAILED
    assert failed.failure_code == "rule_error"
    assert case.status is DecisionCaseStatus.CREATED
    with pytest.raises(DomainError) as error:
        completed.complete()
    assert error.value.error_code == "invalid_decision_case_state"


@pytest.mark.parametrize("field", ["job_posting_version", "resume_version"])
def test_decision_case_rejects_non_positive_or_boolean_versions(field: str) -> None:
    values = _case_kwargs()
    values[field] = False

    with pytest.raises(DomainError) as error:
        DecisionCase.create(**values)
    assert error.value.error_code == "invalid_version"


class _DecisionRepository:
    def __init__(self) -> None:
        self.items: dict[str, DecisionCase] = {}
        self.add_count = 0

    async def add(self, decision_case: DecisionCase) -> DecisionCase:
        self.add_count += 1
        self.items[decision_case.input_fingerprint] = decision_case
        return decision_case

    async def get_by_id(self, case_id: UUID) -> DecisionCase | None:
        return next((item for item in self.items.values() if item.id == case_id), None)

    async def get_by_input_fingerprint(self, fingerprint: str) -> DecisionCase | None:
        return self.items.get(fingerprint)

    async def commit(self) -> None:
        return None


class _PostingRepository:
    def __init__(self, posting: JobPosting | None) -> None:
        self.posting = posting

    async def get_by_id(self, posting_id: UUID) -> JobPosting | None:
        if self.posting is not None and self.posting.id == posting_id:
            return self.posting
        return None


class _RequirementRepository:
    def __init__(self, snapshot: JobRequirementSnapshot | None) -> None:
        self.snapshot = snapshot

    async def get_version(self, posting_id: UUID, version: int) -> JobRequirementSnapshot | None:
        if (
            self.snapshot is not None
            and self.snapshot.job_posting_id == posting_id
            and self.snapshot.version == version
        ):
            return self.snapshot
        return None


class _ProfileRepository:
    def __init__(self, profile: CandidateProfile | None) -> None:
        self.profile = profile

    async def get_version(self, version: int) -> CandidateProfile | None:
        if self.profile is not None and self.profile.version == version:
            return self.profile
        return None


class _ResumeRepository:
    def __init__(self, resume: ResumeVersion | None) -> None:
        self.resume = resume

    async def get_by_id(self, resume_id: UUID) -> ResumeVersion | None:
        if self.resume is not None and self.resume.id == resume_id:
            return self.resume
        return None


def _use_case_fixture() -> tuple[
    CreateDecisionCaseCommand,
    _DecisionRepository,
    JobPosting,
    JobRequirementSnapshot,
    CandidateProfile,
    ResumeVersion,
]:
    owner_id = uuid4()
    posting = JobPosting.create(owner_id=owner_id, jd_text="Python backend role")
    requirement = JobRequirementSnapshot.create(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        content=_requirement_content(),
    )
    profile = CandidateProfile.create(owner_id=owner_id, content=_profile_content())
    resume = ResumeVersion.publish(profile=profile, title="Backend CV", version=1)
    command = CreateDecisionCaseCommand(
        owner_id=owner_id,
        job_posting_id=posting.id,
        job_posting_version=posting.version,
        job_requirement_snapshot_id=requirement.id,
        job_requirement_snapshot_version=requirement.version,
        candidate_profile_id=profile.id,
        candidate_profile_version=profile.version,
        resume_version_id=resume.id,
        resume_version=resume.version,
        rule_set_version="rules-v1",
    )
    return command, _DecisionRepository(), posting, requirement, profile, resume


@pytest.mark.asyncio
async def test_create_decision_case_validates_inputs_and_replays_fingerprint() -> None:
    command, repository, posting, requirement, profile, resume = _use_case_fixture()
    use_case = CreateDecisionCaseUseCase(
        repository,
        _PostingRepository(posting),
        _RequirementRepository(requirement),
        _ProfileRepository(profile),
        _ResumeRepository(resume),
    )

    first = await use_case.execute(command)
    replay = await use_case.execute(command)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.decision_case.id == first.decision_case.id
    assert repository.add_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_input", ["posting", "requirement", "profile", "resume"])
async def test_create_decision_case_hides_foreign_inputs(invalid_input: str) -> None:
    command, repository, posting, requirement, profile, resume = _use_case_fixture()
    foreign_owner = uuid4()
    inputs = {
        "posting": replace(posting, owner_id=foreign_owner),
        "requirement": replace(requirement, owner_id=foreign_owner),
        "profile": replace(profile, owner_id=foreign_owner),
        "resume": replace(resume, owner_id=foreign_owner),
    }
    use_case = CreateDecisionCaseUseCase(
        repository,
        _PostingRepository(inputs["posting"] if invalid_input == "posting" else posting),
        _RequirementRepository(
            inputs["requirement"] if invalid_input == "requirement" else requirement
        ),
        _ProfileRepository(inputs["profile"] if invalid_input == "profile" else profile),
        _ResumeRepository(inputs["resume"] if invalid_input == "resume" else resume),
    )

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(command)
    assert error.value.error_code == "entity_not_found"


@pytest.mark.asyncio
async def test_create_decision_case_requires_resume_from_selected_profile_version() -> None:
    command, repository, posting, requirement, profile, resume = _use_case_fixture()
    unrelated_resume = replace(resume, candidate_profile_id=uuid4())
    use_case = CreateDecisionCaseUseCase(
        repository,
        _PostingRepository(posting),
        _RequirementRepository(requirement),
        _ProfileRepository(profile),
        _ResumeRepository(unrelated_resume),
    )

    with pytest.raises(ApplicationError) as error:
        await use_case.execute(command)
    assert error.value.error_code == "entity_not_found"


@pytest.mark.asyncio
async def test_get_decision_case_hides_foreign_case() -> None:
    decision_case = DecisionCase.create(**_case_kwargs())
    repository = _DecisionRepository()
    repository.items[decision_case.input_fingerprint] = decision_case

    restored = await GetDecisionCaseUseCase(repository).execute(
        GetDecisionCaseQuery(owner_id=decision_case.owner_id, case_id=decision_case.id)
    )
    assert restored == decision_case

    with pytest.raises(ApplicationError) as error:
        await GetDecisionCaseUseCase(repository).execute(
            GetDecisionCaseQuery(owner_id=uuid4(), case_id=decision_case.id)
        )
    assert error.value.error_code == "entity_not_found"
