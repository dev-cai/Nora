"""审计型 Agent Run、Approval 与 Checkpoint 领域记录。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class AgentToolKind(StrEnum):
    READ = "read"
    COMPUTE = "compute"
    WRITE = "write"


class AgentToolCallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: UUID
    owner_id: UUID
    user_goal: str
    thread_id: str
    status: AgentRunStatus
    next_action: str | None
    stop_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, owner_id: UUID, user_goal: str, now: datetime | None = None) -> "AgentRun":
        goal = user_goal.strip()
        if not goal:
            raise DomainError("Agent goal is empty", error_code=ErrorCode.EMPTY_CONTENT)
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        run_id = uuid4()
        return cls(
            id=run_id,
            owner_id=owner_id,
            user_goal=goal,
            thread_id=str(run_id),
            status=AgentRunStatus.RUNNING,
            next_action="route_goal",
            stop_reason=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def transition(
        self,
        status: AgentRunStatus,
        *,
        next_action: str | None = None,
        stop_reason: str | None = None,
        now: datetime | None = None,
    ) -> "AgentRun":
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return AgentRun(
            self.id,
            self.owner_id,
            self.user_goal,
            self.thread_id,
            status,
            next_action,
            stop_reason,
            self.created_at,
            timestamp,
        )


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    id: UUID
    run_id: UUID
    owner_id: UUID
    tool_name: str
    kind: AgentToolKind
    input_payload: dict[str, object]
    input_fingerprint: str
    status: AgentToolCallStatus
    result_ref: str | None
    result_summary: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def start(
        cls,
        *,
        run_id: UUID,
        owner_id: UUID,
        tool_name: str,
        kind: AgentToolKind,
        input_payload: dict[str, object],
        now: datetime | None = None,
    ) -> "AgentToolCall":
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        fingerprint = sha256(
            json.dumps(
                input_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            uuid4(),
            run_id,
            owner_id,
            tool_name,
            kind,
            dict(input_payload),
            fingerprint,
            AgentToolCallStatus.STARTED,
            None,
            None,
            None,
            timestamp,
            None,
        )

    def succeed(
        self, *, result_ref: str, result_summary: str, now: datetime | None = None
    ) -> "AgentToolCall":
        completion_timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return AgentToolCall(
            self.id,
            self.run_id,
            self.owner_id,
            self.tool_name,
            self.kind,
            self.input_payload,
            self.input_fingerprint,
            AgentToolCallStatus.SUCCEEDED,
            result_ref,
            result_summary,
            None,
            self.created_at,
            completion_timestamp,
        )

    def fail(self, *, error_code: str, now: datetime | None = None) -> "AgentToolCall":
        completion_timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return AgentToolCall(
            self.id,
            self.run_id,
            self.owner_id,
            self.tool_name,
            self.kind,
            self.input_payload,
            self.input_fingerprint,
            AgentToolCallStatus.FAILED,
            None,
            None,
            error_code,
            self.created_at,
            completion_timestamp,
        )


@dataclass(frozen=True, slots=True)
class AgentApproval:
    id: UUID
    run_id: UUID
    tool_call_id: UUID
    owner_id: UUID
    target_type: str
    target_id: UUID | None
    target_version: int | None
    action_summary: str
    input_fingerprint: str
    status: AgentApprovalStatus
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def pending(
        cls,
        *,
        run_id: UUID,
        tool_call_id: UUID,
        owner_id: UUID,
        target_type: str,
        target_id: UUID | None,
        target_version: int | None,
        action_summary: str,
        input_fingerprint: str,
        now: datetime | None = None,
    ) -> "AgentApproval":
        if not action_summary.strip() or not input_fingerprint:
            raise DomainError("Approval snapshot is invalid", error_code=ErrorCode.VALIDATION_ERROR)
        return cls(
            uuid4(),
            run_id,
            tool_call_id,
            owner_id,
            target_type,
            target_id,
            target_version,
            action_summary.strip(),
            input_fingerprint,
            AgentApprovalStatus.PENDING,
            (now or datetime.now(timezone.utc)).astimezone(timezone.utc),
            None,
        )

    def decide(self, status: AgentApprovalStatus, now: datetime | None = None) -> "AgentApproval":
        if self.status is not AgentApprovalStatus.PENDING:
            return self
        if status not in (AgentApprovalStatus.APPROVED, AgentApprovalStatus.REJECTED):
            raise DomainError("Approval decision is invalid", error_code=ErrorCode.VALIDATION_ERROR)
        return AgentApproval(
            self.id,
            self.run_id,
            self.tool_call_id,
            self.owner_id,
            self.target_type,
            self.target_id,
            self.target_version,
            self.action_summary,
            self.input_fingerprint,
            status,
            self.created_at,
            (now or datetime.now(timezone.utc)).astimezone(timezone.utc),
        )

    def consume(self, now: datetime | None = None) -> "AgentApproval":
        if self.status is not AgentApprovalStatus.APPROVED:
            raise DomainError("Approval is not approved", error_code=ErrorCode.VALIDATION_ERROR)
        return AgentApproval(
            self.id,
            self.run_id,
            self.tool_call_id,
            self.owner_id,
            self.target_type,
            self.target_id,
            self.target_version,
            self.action_summary,
            self.input_fingerprint,
            AgentApprovalStatus.CONSUMED,
            self.created_at,
            self.decided_at,
        )


@dataclass(frozen=True, slots=True)
class AgentCheckpoint:
    id: UUID
    run_id: UUID
    owner_id: UUID
    step: str
    state: dict[str, object]
    next_action: str | None
    stop_reason: str | None
    created_at: datetime

    @classmethod
    def save(
        cls,
        *,
        run_id: UUID,
        owner_id: UUID,
        step: str,
        state: dict[str, object],
        next_action: str | None,
        stop_reason: str | None,
        now: datetime | None = None,
    ) -> "AgentCheckpoint":
        return cls(
            uuid4(),
            run_id,
            owner_id,
            step,
            dict(state),
            next_action,
            stop_reason,
            (now or datetime.now(timezone.utc)).astimezone(timezone.utc),
        )


__all__ = (
    "AgentApproval",
    "AgentApprovalStatus",
    "AgentCheckpoint",
    "AgentRun",
    "AgentRunStatus",
    "AgentToolCall",
    "AgentToolCallStatus",
    "AgentToolKind",
)
