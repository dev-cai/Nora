"""ResumeVersion 领域与应用用例测试。"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.application.career import (
    GetResumeVersionQuery,
    GetResumeVersionUseCase,
    ListResumeVersionsQuery,
    ListResumeVersionsUseCase,
    PublishResumeVersionCommand,
    PublishResumeVersionUseCase,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import CandidateProfile, ResumeVersion


def _profile_content(skill_name: str = "Python") -> dict[str, object]:
    return {
        "basic_information": {
            "display_name": {"value": "Alice", "confirmation_status": "confirmed"},
            "current_location": {"value": "Shanghai", "confirmation_status": "unconfirmed"},
        },
        "preferences": {
            "target_roles": {
                "value": ["Backend Engineer"],
                "confirmation_status": "confirmed",
            }
        },
        "education": [
            {
                "id": "education-1",
                "school": {"value": "Example University", "confirmation_status": "confirmed"},
                "degree": {"value": "BS", "confirmation_status": "confirmed"},
                "major": {"value": "Computer Science", "confirmation_status": "unconfirmed"},
            }
        ],
        "experiences": [
            {
                "id": "experience-1",
                "company": {"value": "Example Corp", "confirmation_status": "confirmed"},
                "job_title": {"value": "Engineer", "confirmation_status": "confirmed"},
                "responsibilities": {
                    "value": ["Build APIs"],
                    "confirmation_status": "confirmed",
                },
            }
        ],
        "skills": [
            {
                "id": "skill-1",
                "name": {"value": skill_name, "confirmation_status": "confirmed"},
                "years": {"value": 5, "confirmation_status": "unconfirmed"},
            }
        ],
    }


def test_resume_publishes_confirmed_only_immutable_snapshot() -> None:
    now = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
    profile = CandidateProfile.create(owner_id=uuid4(), content=_profile_content())
    resume = ResumeVersion.publish(profile=profile, title="  Backend   Resume ", version=1, now=now)

    assert resume.title == "Backend Resume"
    assert resume.candidate_profile_id == profile.id
    assert resume.profile_version == 1
    assert resume.content == {
        "basic_information": {"display_name": "Alice"},
        "education": [{"id": "education-1", "school": "Example University", "degree": "BS"}],
        "experiences": [
            {
                "id": "experience-1",
                "company": "Example Corp",
                "job_title": "Engineer",
                "responsibilities": ["Build APIs"],
            }
        ],
        "skills": [{"id": "skill-1", "name": "Python"}],
    }
    assert "preferences" not in resume.content
    changed = resume.content
    changed["basic_information"] = {}
    assert resume.content["basic_information"] == {"display_name": "Alice"}
    with pytest.raises(FrozenInstanceError):
        setattr(resume, "title", "Changed")


def test_resume_rejects_profiles_without_confirmed_resume_facts() -> None:
    content = _profile_content()
    content["basic_information"] = {
        "display_name": {"value": "Alice", "confirmation_status": "unconfirmed"},
        "current_location": {"value": "Shanghai", "confirmation_status": "unconfirmed"},
    }
    content["skills"] = []
    content["education"] = []
    content["experiences"] = []
    profile = CandidateProfile.create(owner_id=uuid4(), content=content)

    with pytest.raises(DomainError) as error:
        ResumeVersion.publish(profile=profile, title="Resume", version=1)

    assert error.value.error_code == "profile_has_no_confirmed_data"


class MemoryProfileRepository:
    def __init__(self, profile: CandidateProfile | None) -> None:
        self.profile = profile

    async def get_latest(self) -> CandidateProfile | None:
        return self.profile

    async def get_version(self, version: int) -> CandidateProfile | None:
        if self.profile is not None and self.profile.version == version:
            return self.profile
        return None

    async def add(self, profile: CandidateProfile) -> CandidateProfile:
        self.profile = profile
        return profile

    async def commit(self) -> None:
        return None


class MemoryResumeRepository:
    def __init__(self) -> None:
        self.items: list[ResumeVersion] = []

    async def publish(self, profile: CandidateProfile, title: str) -> ResumeVersion:
        resume = ResumeVersion.publish(profile=profile, title=title, version=len(self.items) + 1)
        self.items.append(resume)
        return resume

    async def get_by_id(self, resume_id: UUID) -> ResumeVersion | None:
        return next((item for item in self.items if item.id == resume_id), None)

    async def list(self, *, offset: int, limit: int) -> list[ResumeVersion]:
        return list(reversed(self.items))[offset : offset + limit]

    async def count(self) -> int:
        return len(self.items)

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_resume_use_cases_publish_list_and_get() -> None:
    profile = CandidateProfile.create(owner_id=uuid4(), content=_profile_content())
    profiles = MemoryProfileRepository(profile)
    resumes = MemoryResumeRepository()

    published = await PublishResumeVersionUseCase(profiles, resumes).execute(
        PublishResumeVersionCommand(
            owner_id=profile.owner_id,
            profile_version=1,
            title="Backend Resume",
        )
    )
    fetched = await GetResumeVersionUseCase(resumes).execute(
        GetResumeVersionQuery(owner_id=profile.owner_id, resume_id=published.id)
    )
    listed = await ListResumeVersionsUseCase(resumes).execute(
        ListResumeVersionsQuery(owner_id=profile.owner_id)
    )

    assert fetched == published
    assert listed.items == (published,)
    assert listed.total == 1


@pytest.mark.asyncio
async def test_resume_publish_hides_missing_profile_version() -> None:
    owner_id = uuid4()
    with pytest.raises(ApplicationError) as error:
        await PublishResumeVersionUseCase(
            MemoryProfileRepository(None), MemoryResumeRepository()
        ).execute(
            PublishResumeVersionCommand(
                owner_id=owner_id,
                profile_version=1,
                title="Resume",
            )
        )

    assert error.value.error_code == "entity_not_found"
