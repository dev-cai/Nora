from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from app.application.followup import (
    CreateInterviewCaseCommand,
    InterviewCaseUseCases,
    UpdateInterviewCaseCommand,
)
from app.domain.base.exceptions import ApplicationError, DomainError, ErrorCode
from app.domain.followup import (
    ApplicationRecord,
    ApplicationRecordStatus,
    InterviewCase,
    InterviewCaseStatus,
    InterviewMode,
)

# The use-case create path uses the production clock, so keep this fixture safely future-dated.
NOW = datetime(2099, 1, 1, 4, 0, tzinfo=timezone.utc)
STARTS_AT = NOW + timedelta(days=2)


def make_application(
    status: ApplicationRecordStatus = ApplicationRecordStatus.INTERVIEWING,
) -> ApplicationRecord:
    owner_id = uuid4()
    created = ApplicationRecord.create(
        owner_id=owner_id,
        actor_id=owner_id,
        application_decision_id=uuid4(),
        decision_case_id=uuid4(),
        resume_variant_id=uuid4(),
        resume_variant_version=1,
        variant_content_fingerprint="a" * 64,
        idempotency_key="application",
        now=NOW,
    )
    return ApplicationRecord.restore(
        record_id=created.id,
        owner_id=created.owner_id,
        created_by=created.created_by,
        version=3 if status is ApplicationRecordStatus.INTERVIEWING else 2,
        status=status,
        application_decision_id=created.application_decision_id,
        decision_case_id=created.decision_case_id,
        resume_variant_id=created.resume_variant_id,
        resume_variant_version=created.resume_variant_version,
        variant_content_fingerprint=created.variant_content_fingerprint,
        resume_pdf_id=None,
        resume_pdf_version=None,
        artifact_id=None,
        artifact_version=None,
        artifact_sha256=None,
        message_draft_id=None,
        message_draft_version=None,
        message_content_fingerprint=None,
        idempotency_key=created.idempotency_key,
        request_fingerprint=created.request_fingerprint,
        created_at=created.created_at,
        updated_at=created.updated_at,
    )


def create_case(**overrides: object) -> InterviewCase:
    owner_id = uuid4()
    values: dict[str, object] = {
        "owner_id": owner_id,
        "actor_id": owner_id,
        "application_record_id": uuid4(),
        "starts_at": STARTS_AT,
        "timezone_name": "Asia/Shanghai",
        "mode": InterviewMode.ONLINE,
        "location": None,
        "meeting_url": "https://meet.example.com/private-token",
        "round_number": 1,
        "note": "Bring the project notes",
        "status": InterviewCaseStatus.SCHEDULED,
        "idempotency_key": " interview  create ",
        "now": NOW,
    }
    values.update(overrides)
    return InterviewCase.create(**values)  # type: ignore[arg-type]


def test_interview_case_validates_timezone_mode_round_and_actor() -> None:
    interview = create_case()
    assert interview.version == 1
    assert interview.idempotency_key == "interview  create"
    assert interview.starts_at == STARTS_AT

    invalid_values = [
        ({"timezone_name": "Mars/Olympus"}, ErrorCode.INVALID_INTERVIEW_TIMEZONE),
        ({"round_number": 0}, ErrorCode.INVALID_INTERVIEW_ROUND),
        (
            {"mode": InterviewMode.ONLINE, "meeting_url": None},
            ErrorCode.INVALID_INTERVIEW_CASE,
        ),
        (
            {"mode": InterviewMode.ONSITE, "location": None, "meeting_url": None},
            ErrorCode.INVALID_INTERVIEW_CASE,
        ),
        ({"meeting_url": "http://meet.example.com/token"}, ErrorCode.INVALID_URL),
        ({"actor_id": uuid4()}, ErrorCode.INVALID_INTERVIEW_CASE),
    ]
    for overrides, expected in invalid_values:
        with pytest.raises(DomainError) as exc_info:
            create_case(**overrides)
        assert exc_info.value.error_code is expected


def test_interview_case_update_appends_version_and_past_case_is_immutable() -> None:
    interview = create_case()
    updated = interview.update(
        actor_id=interview.owner_id,
        starts_at=STARTS_AT + timedelta(hours=1),
        timezone_name="Asia/Shanghai",
        mode=InterviewMode.ONSITE,
        location="Shanghai office",
        meeting_url=None,
        round_number=2,
        note="System design round",
        status=InterviewCaseStatus.SCHEDULED,
        idempotency_key="update-1",
        now=NOW,
    )
    assert updated.id == interview.id
    assert updated.version == 2
    assert updated.round_number == 2
    assert interview.mode is InterviewMode.ONLINE

    with pytest.raises(DomainError) as exc_info:
        replace(interview, starts_at=NOW).update(
            actor_id=interview.owner_id,
            starts_at=STARTS_AT,
            timezone_name="Asia/Shanghai",
            mode=InterviewMode.PHONE,
            location=None,
            meeting_url=None,
            round_number=1,
            note=None,
            status=InterviewCaseStatus.SCHEDULED,
            idempotency_key="past-update",
            now=NOW,
        )
    assert exc_info.value.error_code is ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT


@pytest.mark.asyncio
async def test_use_case_requires_interviewing_and_replays_create_and_update() -> None:
    application = make_application()
    interviews = MemoryInterviews()
    audits = MemoryAudits()
    use_cases = InterviewCaseUseCases(
        interviews,
        MemoryApplications(application),
        audits,
        MemoryTransaction(),
    )
    create = CreateInterviewCaseCommand(
        owner_id=application.owner_id,
        actor_id=application.owner_id,
        application_record_id=application.id,
        starts_at=STARTS_AT,
        timezone="Asia/Shanghai",
        mode=InterviewMode.ONLINE,
        location=None,
        meeting_url="https://meet.example.com/private-token",
        round_number=1,
        note="private candidate note",
        status=InterviewCaseStatus.SCHEDULED,
        idempotency_key="create-interview",
    )
    created = await use_cases.create(create)
    replay = await use_cases.create(create)
    update = UpdateInterviewCaseCommand(
        owner_id=application.owner_id,
        actor_id=application.owner_id,
        interview_case_id=created.interview.id,
        base_version=1,
        starts_at=STARTS_AT + timedelta(hours=1),
        timezone="Asia/Shanghai",
        mode=InterviewMode.PHONE,
        location=None,
        meeting_url=None,
        round_number=2,
        note="private updated note",
        status=InterviewCaseStatus.SCHEDULED,
        idempotency_key="update-interview",
    )
    updated = await use_cases.update(update)
    update_replay = await use_cases.update(update)

    assert created.replayed is False
    assert replay.replayed is True
    assert updated.interview.version == 2
    assert update_replay.replayed is True
    assert len(await interviews.list_versions(created.interview.id)) == 2
    assert all("private" not in (event.after_summary or "") for event in audits.items)
    assert all("meet.example.com" not in (event.after_summary or "") for event in audits.items)

    with pytest.raises(ApplicationError) as stale:
        await use_cases.update(replace(update, idempotency_key="stale", round_number=3))
    assert stale.value.error_code is ErrorCode.INTERVIEW_CASE_VERSION_CONFLICT

    applied = replace(application, status=ApplicationRecordStatus.APPLIED)
    blocked = InterviewCaseUseCases(
        MemoryInterviews(),
        MemoryApplications(applied),
        MemoryAudits(),
        MemoryTransaction(),
    )
    with pytest.raises(ApplicationError) as conflict:
        await blocked.create(replace(create, idempotency_key="blocked"))
    assert conflict.value.error_code is ErrorCode.INTERVIEW_CASE_APPLICATION_CONFLICT


class MemoryInterviews:
    def __init__(self) -> None:
        self.items: list[InterviewCase] = []

    async def add(self, interview: InterviewCase) -> InterviewCase:
        if any(
            item.id == interview.id and item.version == interview.version for item in self.items
        ):
            raise AssertionError("duplicate version")
        self.items.append(interview)
        return interview

    async def get_latest(self, interview_id: UUID) -> InterviewCase | None:
        versions = [item for item in self.items if item.id == interview_id]
        return max(versions, key=lambda item: item.version, default=None)

    async def get_version(self, interview_id: UUID, version: int) -> InterviewCase | None:
        return next(
            (item for item in self.items if item.id == interview_id and item.version == version),
            None,
        )

    async def get_by_idempotency_key(self, key: str) -> InterviewCase | None:
        return next((item for item in self.items if item.idempotency_key == key), None)

    async def list_latest(self, *, offset: int, limit: int) -> list[InterviewCase]:
        latest = {item.id: item for item in sorted(self.items, key=lambda item: item.version)}
        return list(latest.values())[offset : offset + limit]

    async def list_versions(self, interview_id: UUID) -> list[InterviewCase]:
        return sorted(
            (item for item in self.items if item.id == interview_id),
            key=lambda item: item.version,
            reverse=True,
        )

    async def count(self) -> int:
        return len({item.id for item in self.items})


class MemoryApplications:
    def __init__(self, application: ApplicationRecord) -> None:
        self.application = application

    async def get_by_id(self, record_id: UUID) -> ApplicationRecord | None:
        return self.application if record_id == self.application.id else None


class MemoryAudits:
    def __init__(self) -> None:
        self.items: list[object] = []

    async def add(self, event: object) -> object:
        self.items.append(event)
        return event


class MemoryTransaction:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None
