"""CandidateProfile 领域与应用服务测试。"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.career import (
    GetCandidateProfileQuery,
    GetCandidateProfileUseCase,
    PutCandidateProfileCommand,
    PutCandidateProfileUseCase,
    confirmed_profile_data,
)
from app.domain.base.exceptions import ApplicationError, DomainError
from app.domain.career import CandidateProfile


def profile_content(status: str = "unconfirmed") -> dict[str, object]:
    return {
        "basic_information": {
            "display_name": {"value": "Alice", "confirmation_status": status},
            "current_location": {"value": "Shanghai", "confirmation_status": "confirmed"},
        },
        "skills": [
            {
                "id": "skill-1",
                "name": {"value": "Python", "confirmation_status": "confirmed"},
                "years": {"value": 5, "confirmation_status": "unconfirmed"},
            }
        ],
    }


def test_profile_enriches_user_input_and_confirmed_data() -> None:
    owner_id = uuid4()
    now = datetime(2026, 8, 3, 1, 2, tzinfo=timezone.utc)
    profile = CandidateProfile.create(owner_id=owner_id, content=profile_content(), now=now)

    display_name = profile.content["basic_information"]["display_name"]
    assert display_name["source_type"] == "user_input"
    assert display_name["updated_at"] == now.isoformat()
    assert confirmed_profile_data(profile) == {
        "basic_information": {"current_location": "Shanghai"},
        "skills": [{"id": "skill-1", "name": "Python"}],
    }


def test_profile_updates_append_version_and_preserve_creation_time() -> None:
    created = datetime(2026, 8, 3, 1, 2, tzinfo=timezone.utc)
    updated = datetime(2026, 8, 4, 1, 2, tzinfo=timezone.utc)
    profile = CandidateProfile.create(owner_id=uuid4(), content=profile_content(), now=created)
    next_profile = profile.next_version(
        content=profile_content("confirmed"),
        now=updated,
    )

    assert next_profile.id == profile.id
    assert next_profile.version == 2
    assert next_profile.created_at == created
    assert next_profile.updated_at == updated


def test_profile_only_refreshes_changed_fact_timestamps() -> None:
    created = datetime(2026, 8, 3, 1, 2, tzinfo=timezone.utc)
    updated = datetime(2026, 8, 4, 1, 2, tzinfo=timezone.utc)
    profile = CandidateProfile.create(owner_id=uuid4(), content=profile_content(), now=created)
    changed = profile_content("confirmed")
    next_profile = profile.next_version(content=changed, now=updated)

    previous_content = profile.content
    next_content = next_profile.content
    assert next_content["basic_information"]["display_name"]["updated_at"] == updated.isoformat()
    assert (
        next_content["basic_information"]["current_location"]["updated_at"]
        == previous_content["basic_information"]["current_location"]["updated_at"]
    )
    assert (
        next_content["skills"][0]["name"]["updated_at"]
        == previous_content["skills"][0]["name"]["updated_at"]
    )


def test_superseded_fact_cannot_be_restored() -> None:
    profile = CandidateProfile.create(owner_id=uuid4(), content=profile_content("superseded"))

    with pytest.raises(DomainError) as error:
        profile.next_version(content=profile_content("confirmed"))

    assert error.value.error_code == "invalid_confirmation_transition"


@pytest.mark.parametrize(
    "items",
    [
        [{"name": {"value": "Python", "confirmation_status": "confirmed"}}],
        [
            {"id": "same", "name": {"value": "Python", "confirmation_status": "confirmed"}},
            {"id": "same", "name": {"value": "Go", "confirmation_status": "confirmed"}},
        ],
    ],
)
def test_profile_rejects_missing_or_duplicate_collection_item_ids(
    items: list[dict[str, object]],
) -> None:
    content = profile_content()
    content["skills"] = items

    with pytest.raises(DomainError) as error:
        CandidateProfile.create(owner_id=uuid4(), content=content)

    assert error.value.error_code == "invalid_profile_item_id"


class MemoryProfileRepository:
    def __init__(self) -> None:
        self.items: list[CandidateProfile] = []

    async def get_latest(self) -> CandidateProfile | None:
        return self.items[-1] if self.items else None

    async def get_version(self, version: int) -> CandidateProfile | None:
        return next((item for item in self.items if item.version == version), None)

    async def add(self, profile: CandidateProfile) -> CandidateProfile:
        self.items.append(profile)
        return profile

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_profile_use_cases_create_update_and_read_history() -> None:
    owner_id = uuid4()
    repository = MemoryProfileRepository()
    put = PutCandidateProfileUseCase(repository)
    get = GetCandidateProfileUseCase(repository)

    first = await put.execute(
        PutCandidateProfileCommand(owner_id=owner_id, content=profile_content())
    )
    second = await put.execute(
        PutCandidateProfileCommand(owner_id=owner_id, content=profile_content("confirmed"))
    )

    assert first.version == 1
    assert second.version == 2
    assert (await get.execute(GetCandidateProfileQuery(owner_id=owner_id, version=1))).version == 1


@pytest.mark.asyncio
async def test_profile_use_case_hides_missing_and_other_owner_versions() -> None:
    owner_id = uuid4()
    repository = MemoryProfileRepository()
    await PutCandidateProfileUseCase(repository).execute(
        PutCandidateProfileCommand(owner_id=owner_id, content=profile_content())
    )

    with pytest.raises(ApplicationError) as error:
        await GetCandidateProfileUseCase(repository).execute(
            GetCandidateProfileQuery(owner_id=uuid4())
        )
    assert error.value.error_code == "entity_not_found"
