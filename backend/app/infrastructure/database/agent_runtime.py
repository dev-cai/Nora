"""PostgreSQL persistence for Agent Run, ToolCall, Approval and Checkpoint facts."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.agent_runtime import (
    AgentApproval,
    AgentApprovalStatus,
    AgentCheckpoint,
    AgentRun,
    AgentRunStatus,
    AgentToolCall,
    AgentToolCallStatus,
    AgentToolKind,
)
from app.infrastructure.database.base import Base


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_owner_created", "owner_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    next_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentToolCallRecord(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (Index("ix_agent_tool_calls_run_created", "run_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentApprovalRecord(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (Index("ix_agent_approvals_run_status", "run_id", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_call_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_tool_calls.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    target_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentCheckpointRecord(Base):
    __tablename__ = "agent_checkpoints"
    __table_args__ = (Index("ix_agent_checkpoints_run_created", "run_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    next_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyAgentRuntimeRepository:
    """用户范围 Agent Runtime facts; deleting checkpoints never touches business tables."""

    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session, self.owner_id = session, owner_id

    async def add_run(self, run: AgentRun) -> AgentRun:
        self._check_owner(run.owner_id)
        self.session.add(AgentRunRecord(**_run_values(run)))
        await self.session.flush()
        return run

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        record = await self.session.scalar(
            select(AgentRunRecord).where(
                AgentRunRecord.id == run_id, AgentRunRecord.owner_id == self.owner_id
            )
        )
        return _run_domain(record) if record else None

    async def update_run(self, run: AgentRun) -> AgentRun:
        self._check_owner(run.owner_id)
        record = await self.session.scalar(
            select(AgentRunRecord)
            .where(AgentRunRecord.id == run.id, AgentRunRecord.owner_id == self.owner_id)
            .with_for_update()
        )
        if record is None:
            raise ValueError("Agent run not found")
        for key, value in _run_values(run).items():
            setattr(record, key, value)
        await self.session.flush()
        return run

    async def add_tool_call(self, tool_call: AgentToolCall) -> AgentToolCall:
        self._check_owner(tool_call.owner_id)
        self.session.add(AgentToolCallRecord(**_tool_call_values(tool_call)))
        await self.session.flush()
        return tool_call

    async def update_tool_call(self, tool_call: AgentToolCall) -> AgentToolCall:
        self._check_owner(tool_call.owner_id)
        record = await self.session.scalar(
            select(AgentToolCallRecord)
            .where(
                AgentToolCallRecord.id == tool_call.id,
                AgentToolCallRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ValueError("Agent tool call not found")
        for key, value in _tool_call_values(tool_call).items():
            setattr(record, key, value)
        await self.session.flush()
        return tool_call

    async def list_tool_calls(self, run_id: UUID) -> list[AgentToolCall]:
        records = await self.session.scalars(
            select(AgentToolCallRecord)
            .where(
                AgentToolCallRecord.run_id == run_id,
                AgentToolCallRecord.owner_id == self.owner_id,
            )
            .order_by(AgentToolCallRecord.created_at)
        )
        return [_tool_call_domain(record) for record in records]

    async def add_approval(self, approval: AgentApproval) -> AgentApproval:
        self._check_owner(approval.owner_id)
        self.session.add(AgentApprovalRecord(**_approval_values(approval)))
        await self.session.flush()
        return approval

    async def get_approval(self, approval_id: UUID) -> AgentApproval | None:
        record = await self.session.scalar(
            select(AgentApprovalRecord).where(
                AgentApprovalRecord.id == approval_id,
                AgentApprovalRecord.owner_id == self.owner_id,
            )
        )
        return _approval_domain(record) if record else None

    async def get_pending_approval(self, run_id: UUID) -> AgentApproval | None:
        record = await self.session.scalar(
            select(AgentApprovalRecord).where(
                AgentApprovalRecord.run_id == run_id,
                AgentApprovalRecord.owner_id == self.owner_id,
                AgentApprovalRecord.status == AgentApprovalStatus.PENDING.value,
            )
        )
        return _approval_domain(record) if record else None

    async def get_latest_approval(self, run_id: UUID) -> AgentApproval | None:
        record = await self.session.scalar(
            select(AgentApprovalRecord)
            .where(
                AgentApprovalRecord.run_id == run_id,
                AgentApprovalRecord.owner_id == self.owner_id,
            )
            .order_by(AgentApprovalRecord.created_at.desc())
            .limit(1)
        )
        return _approval_domain(record) if record else None

    async def update_approval(self, approval: AgentApproval) -> AgentApproval:
        self._check_owner(approval.owner_id)
        record = await self.session.scalar(
            select(AgentApprovalRecord)
            .where(
                AgentApprovalRecord.id == approval.id,
                AgentApprovalRecord.owner_id == self.owner_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ValueError("Agent approval not found")
        for key, value in _approval_values(approval).items():
            setattr(record, key, value)
        await self.session.flush()
        return approval

    async def add_checkpoint(self, checkpoint: AgentCheckpoint) -> AgentCheckpoint:
        self._check_owner(checkpoint.owner_id)
        self.session.add(AgentCheckpointRecord(**_checkpoint_values(checkpoint)))
        await self.session.flush()
        return checkpoint

    async def get_latest_checkpoint(self, run_id: UUID) -> AgentCheckpoint | None:
        record = await self.session.scalar(
            select(AgentCheckpointRecord)
            .where(
                AgentCheckpointRecord.run_id == run_id,
                AgentCheckpointRecord.owner_id == self.owner_id,
            )
            .order_by(AgentCheckpointRecord.created_at.desc())
            .limit(1)
        )
        return _checkpoint_domain(record) if record else None

    async def delete_checkpoints(self, run_id: UUID) -> None:
        records = await self.session.scalars(
            select(AgentCheckpointRecord).where(
                AgentCheckpointRecord.run_id == run_id,
                AgentCheckpointRecord.owner_id == self.owner_id,
            )
        )
        for record in records:
            await self.session.delete(record)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    def _check_owner(self, owner_id: UUID) -> None:
        if owner_id != self.owner_id:
            raise ValueError("Agent fact is outside user scope")


def _run_values(value: AgentRun) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "user_goal": value.user_goal,
        "thread_id": value.thread_id,
        "status": value.status.value,
        "next_action": value.next_action,
        "stop_reason": value.stop_reason,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
    }


def _run_domain(value: AgentRunRecord) -> AgentRun:
    return AgentRun(
        value.id,
        value.owner_id,
        value.user_goal,
        value.thread_id,
        AgentRunStatus(value.status),
        value.next_action,
        value.stop_reason,
        _utc(value.created_at),
        _utc(value.updated_at),
    )


def _tool_call_values(value: AgentToolCall) -> dict[str, object]:
    return {
        "id": value.id,
        "run_id": value.run_id,
        "owner_id": value.owner_id,
        "tool_name": value.tool_name,
        "kind": value.kind.value,
        "input_payload": value.input_payload,
        "input_fingerprint": value.input_fingerprint,
        "status": value.status.value,
        "result_ref": value.result_ref,
        "result_summary": value.result_summary,
        "error_code": value.error_code,
        "created_at": value.created_at,
        "completed_at": value.completed_at,
    }


def _tool_call_domain(value: AgentToolCallRecord) -> AgentToolCall:
    return AgentToolCall(
        value.id,
        value.run_id,
        value.owner_id,
        value.tool_name,
        AgentToolKind(value.kind),
        dict(value.input_payload),
        value.input_fingerprint,
        AgentToolCallStatus(value.status),
        value.result_ref,
        value.result_summary,
        value.error_code,
        _utc(value.created_at),
        _utc(value.completed_at) if value.completed_at else None,
    )


def _approval_values(value: AgentApproval) -> dict[str, object]:
    return {
        "id": value.id,
        "run_id": value.run_id,
        "tool_call_id": value.tool_call_id,
        "owner_id": value.owner_id,
        "target_type": value.target_type,
        "target_id": value.target_id,
        "target_version": value.target_version,
        "action_summary": value.action_summary,
        "input_fingerprint": value.input_fingerprint,
        "status": value.status.value,
        "created_at": value.created_at,
        "decided_at": value.decided_at,
    }


def _approval_domain(value: AgentApprovalRecord) -> AgentApproval:
    return AgentApproval(
        value.id,
        value.run_id,
        value.tool_call_id,
        value.owner_id,
        value.target_type,
        value.target_id,
        value.target_version,
        value.action_summary,
        value.input_fingerprint,
        AgentApprovalStatus(value.status),
        _utc(value.created_at),
        _utc(value.decided_at) if value.decided_at else None,
    )


def _checkpoint_values(value: AgentCheckpoint) -> dict[str, object]:
    return {
        "id": value.id,
        "run_id": value.run_id,
        "owner_id": value.owner_id,
        "step": value.step,
        "state": value.state,
        "next_action": value.next_action,
        "stop_reason": value.stop_reason,
        "created_at": value.created_at,
    }


def _checkpoint_domain(value: AgentCheckpointRecord) -> AgentCheckpoint:
    return AgentCheckpoint(
        value.id,
        value.run_id,
        value.owner_id,
        value.step,
        dict(value.state),
        value.next_action,
        value.stop_reason,
        _utc(value.created_at),
    )


__all__ = (
    "AgentApprovalRecord",
    "AgentCheckpointRecord",
    "AgentRunRecord",
    "AgentToolCallRecord",
    "SqlAlchemyAgentRuntimeRepository",
)
