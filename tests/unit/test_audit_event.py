"""审计事件领域规则测试。"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from nora.domain.base.exceptions import DomainError
from nora.domain.governance import AuditAction, AuditEvent


def test_audit_event_create_is_immutable_and_serializable() -> None:
    actor_id = uuid4()
    target_id = uuid4()
    occurred_at = datetime(2026, 7, 30, 8, 30, tzinfo=timezone.utc)

    event = AuditEvent.create(
        actor_id=actor_id,
        action=AuditAction.CREATE,
        target_type=" job_posting ",
        target_id=target_id,
        after_summary='{"status":"active"}',
        idempotency_key=" job-1 ",
        now=occurred_at,
    )

    assert event.to_dict() == {
        "id": str(event.id),
        "actor_id": str(actor_id),
        "action": "create",
        "target_type": "job_posting",
        "target_id": str(target_id),
        "before_summary": None,
        "after_summary": '{"status":"active"}',
        "occurred_at": "2026-07-30T08:30:00+00:00",
        "idempotency_key": "job-1",
    }
    with pytest.raises(FrozenInstanceError):
        event.target_type = "changed"  # type: ignore[misc]


def test_audit_event_rejects_naive_timestamp() -> None:
    with pytest.raises(DomainError) as error:
        AuditEvent.create(
            actor_id=uuid4(),
            action=AuditAction.CREATE,
            target_type="job_posting",
            target_id=uuid4(),
            now=datetime(2026, 7, 30, 8, 30),
        )

    assert error.value.error_code == "invalid_timestamp"
