from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.domain.base.exceptions import DomainError, ErrorCode
from app.domain.followup import ApplicationRecord, ApplicationRecordStatus

NOW = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def make_record(**overrides: object) -> ApplicationRecord:
    owner_id = uuid4()
    values: dict[str, object] = {
        "owner_id": owner_id,
        "actor_id": owner_id,
        "application_decision_id": uuid4(),
        "decision_case_id": uuid4(),
        "resume_variant_id": uuid4(),
        "resume_variant_version": 1,
        "variant_content_fingerprint": SHA,
        "idempotency_key": " create  request ",
        "now": NOW,
    }
    values.update(overrides)
    return ApplicationRecord.create(**values)  # type: ignore[arg-type]


def test_create_planned_record_normalizes_key_and_fixes_material_versions() -> None:
    pdf_id, artifact_id, draft_id = uuid4(), uuid4(), uuid4()
    record = make_record(
        resume_pdf_id=pdf_id,
        resume_pdf_version=2,
        artifact_id=artifact_id,
        artifact_version=3,
        artifact_sha256="B" * 64,
        message_draft_id=draft_id,
        message_draft_version=4,
        message_content_fingerprint="C" * 64,
    )

    assert record.status is ApplicationRecordStatus.PLANNED
    assert record.version == 1
    assert record.idempotency_key == "create  request"
    assert record.resume_pdf_id == pdf_id
    assert record.artifact_sha256 == "b" * 64
    assert record.message_draft_version == 4


@pytest.mark.parametrize(
    ("start", "allowed"),
    [
        ("planned", {"applied", "withdrawn"}),
        ("applied", {"interviewing", "rejected", "withdrawn"}),
        ("interviewing", {"offer_received", "rejected", "withdrawn"}),
        ("offer_received", set()),
        ("rejected", set()),
        ("withdrawn", set()),
    ],
)
def test_transition_matrix(start: str, allowed: set[str]) -> None:
    record = make_record()
    record = ApplicationRecord.restore(
        record_id=record.id,
        owner_id=record.owner_id,
        created_by=record.created_by,
        version=1,
        status=ApplicationRecordStatus(start),
        application_decision_id=record.application_decision_id,
        decision_case_id=record.decision_case_id,
        resume_variant_id=record.resume_variant_id,
        resume_variant_version=record.resume_variant_version,
        variant_content_fingerprint=record.variant_content_fingerprint,
        resume_pdf_id=None,
        resume_pdf_version=None,
        artifact_id=None,
        artifact_version=None,
        artifact_sha256=None,
        message_draft_id=None,
        message_draft_version=None,
        message_content_fingerprint=None,
        idempotency_key=record.idempotency_key,
        request_fingerprint=record.request_fingerprint,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    for target in ApplicationRecordStatus:
        channel = "company website" if target is ApplicationRecordStatus.APPLIED else None
        if target.value in allowed:
            updated, event = record.transition(
                actor_id=record.owner_id,
                to_status=target,
                occurred_at=NOW,
                channel=channel,
                note=" user confirmed ",
                idempotency_key=f"to-{target}",
                now=NOW,
            )
            assert updated.status is target
            assert updated.version == 2
            assert event.from_status is record.status
            assert event.to_status is target
            assert event.record_version == 2
            assert event.note == "user confirmed"
        else:
            with pytest.raises(DomainError) as exc_info:
                record.transition(
                    actor_id=record.owner_id,
                    to_status=target,
                    occurred_at=NOW,
                    channel=channel,
                    note=None,
                    idempotency_key=f"to-{target}",
                    now=NOW,
                )
            assert exc_info.value.error_code is ErrorCode.APPLICATION_RECORD_TRANSITION_CONFLICT


def test_applied_requires_explicit_channel_and_timezone() -> None:
    record = make_record()
    with pytest.raises(DomainError) as exc_info:
        record.transition(
            actor_id=record.owner_id,
            to_status=ApplicationRecordStatus.APPLIED,
            occurred_at=NOW,
            channel="  ",
            note=None,
            idempotency_key="apply",
        )
    assert exc_info.value.error_code is ErrorCode.INVALID_APPLICATION_RECORD

    with pytest.raises(DomainError) as exc_info:
        record.transition(
            actor_id=record.owner_id,
            to_status=ApplicationRecordStatus.APPLIED,
            occurred_at=NOW.replace(tzinfo=None),
            channel="email",
            note=None,
            idempotency_key="apply",
        )
    assert exc_info.value.error_code is ErrorCode.INVALID_TIMESTAMP


def test_record_and_transition_actor_must_match_owner() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_record(actor_id=uuid4())
    assert exc_info.value.error_code is ErrorCode.INVALID_APPLICATION_RECORD

    record = make_record()
    with pytest.raises(DomainError) as exc_info:
        record.transition(
            actor_id=uuid4(),
            to_status=ApplicationRecordStatus.WITHDRAWN,
            occurred_at=NOW,
            channel=None,
            note=None,
            idempotency_key="foreign-actor",
        )
    assert exc_info.value.error_code is ErrorCode.INVALID_APPLICATION_RECORD


@pytest.mark.parametrize(
    "overrides",
    [
        {"resume_pdf_id": uuid4()},
        {"message_draft_id": uuid4(), "message_draft_version": 1},
    ],
)
def test_material_references_are_all_or_none(overrides: dict[str, object]) -> None:
    with pytest.raises(DomainError) as exc_info:
        make_record(**overrides)
    assert exc_info.value.error_code is ErrorCode.INVALID_APPLICATION_RECORD


def test_transition_request_fingerprint_is_stable_for_replay() -> None:
    record = make_record()
    actor = record.owner_id
    _, first = record.transition(
        actor_id=actor,
        to_status=ApplicationRecordStatus.APPLIED,
        occurred_at=NOW,
        channel=" company  website ",
        note=" sent  manually ",
        idempotency_key="apply  key",
        now=NOW,
    )
    _, replay = record.transition(
        actor_id=actor,
        to_status=ApplicationRecordStatus.APPLIED,
        occurred_at=NOW,
        channel="company website",
        note="sent manually",
        idempotency_key="apply  key",
        now=NOW,
    )

    assert first.has_same_request(replay)
    assert first.idempotency_key == "apply  key"
