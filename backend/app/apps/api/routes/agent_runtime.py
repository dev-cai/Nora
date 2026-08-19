"""Run/Approval API; graph nodes execute only in the Agent Runtime adapter."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime import AgentRuntimeService, AgentRunView
from app.agent_runtime.tools import AgentToolInput
from app.apps.api.dependencies.agent_runtime import get_agent_runtime_service
from app.apps.api.dependencies.common import get_current_user
from app.domain.agent_runtime import AgentRunStatus, AgentToolCallStatus
from app.domain.identity import User

router = APIRouter(prefix="/agent-runs", tags=["agent-runtime"])


class StartAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_goal: str = Field(min_length=1, max_length=4_000)
    interview_case_id: UUID | None = None
    source_id: UUID | None = None
    application_record_id: UUID | None = None
    job_posting_id: UUID | None = None


class AgentToolCallResponse(BaseModel):
    id: UUID
    tool_name: str
    kind: str
    status: AgentToolCallStatus
    input_fingerprint: str
    result_ref: str | None
    result_summary: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class AgentApprovalResponse(BaseModel):
    id: UUID
    tool_call_id: UUID
    target_type: str
    target_id: UUID | None
    target_version: int | None
    action_summary: str
    input_fingerprint: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class AgentCheckpointResponse(BaseModel):
    id: UUID
    step: str
    state: dict[str, object]
    next_action: str | None
    stop_reason: str | None
    created_at: datetime


class AgentRunResponse(BaseModel):
    id: UUID
    user_goal: str
    status: AgentRunStatus
    next_action: str | None
    stop_reason: str | None
    created_at: datetime
    updated_at: datetime
    tool_calls: list[AgentToolCallResponse]
    approval: AgentApprovalResponse | None
    checkpoint: AgentCheckpointResponse | None

    @classmethod
    def from_view(cls, value: AgentRunView) -> "AgentRunResponse":
        return cls(
            id=value.run.id,
            user_goal=value.run.user_goal,
            status=value.run.status,
            next_action=value.run.next_action,
            stop_reason=value.run.stop_reason,
            created_at=value.run.created_at,
            updated_at=value.run.updated_at,
            tool_calls=[
                AgentToolCallResponse(
                    id=item.id,
                    tool_name=item.tool_name,
                    kind=item.kind.value,
                    status=item.status,
                    input_fingerprint=item.input_fingerprint,
                    result_ref=item.result_ref,
                    result_summary=item.result_summary,
                    error_code=item.error_code,
                    created_at=item.created_at,
                    completed_at=item.completed_at,
                )
                for item in value.tool_calls
            ],
            approval=(
                None
                if value.approval is None
                else AgentApprovalResponse(
                    id=value.approval.id,
                    tool_call_id=value.approval.tool_call_id,
                    target_type=value.approval.target_type,
                    target_id=value.approval.target_id,
                    target_version=value.approval.target_version,
                    action_summary=value.approval.action_summary,
                    input_fingerprint=value.approval.input_fingerprint,
                    status=value.approval.status.value,
                    created_at=value.approval.created_at,
                    decided_at=value.approval.decided_at,
                )
            ),
            checkpoint=(
                None
                if value.checkpoint is None
                else AgentCheckpointResponse(
                    id=value.checkpoint.id,
                    step=value.checkpoint.step,
                    state=value.checkpoint.state,
                    next_action=value.checkpoint.next_action,
                    stop_reason=value.checkpoint.stop_reason,
                    created_at=value.checkpoint.created_at,
                )
            ),
        )


@router.post("", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def start_agent_run(
    payload: StartAgentRunRequest,
    response: Response,
    user: User = Depends(get_current_user),
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentRunResponse:
    value = await runtime.start(
        owner_id=user.id,
        user_goal=payload.user_goal,
        tool_input=AgentToolInput(
            user_goal=payload.user_goal,
            interview_case_id=payload.interview_case_id,
            source_id=payload.source_id,
            application_record_id=payload.application_record_id,
            job_posting_id=payload.job_posting_id,
        ),
    )
    if value.run.status is AgentRunStatus.WAITING_APPROVAL:
        response.status_code = status.HTTP_202_ACCEPTED
    return AgentRunResponse.from_view(value)


@router.get("/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: UUID,
    user: User = Depends(get_current_user),
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentRunResponse:
    return AgentRunResponse.from_view(await runtime.view(owner_id=user.id, run_id=run_id))


@router.post("/{run_id}/approvals/{approval_id}/approve", response_model=AgentRunResponse)
async def approve_agent_run(
    run_id: UUID,
    approval_id: UUID,
    user: User = Depends(get_current_user),
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentRunResponse:
    value = await runtime.approve(owner_id=user.id, approval_id=approval_id)
    if value.run.id != run_id:
        from app.domain.base.exceptions import ApplicationError, ErrorCode

        raise ApplicationError(
            "Approval does not belong to Run", error_code=ErrorCode.ENTITY_NOT_FOUND
        )
    return AgentRunResponse.from_view(value)


@router.post("/{run_id}/approvals/{approval_id}/reject", response_model=AgentRunResponse)
async def reject_agent_run(
    run_id: UUID,
    approval_id: UUID,
    user: User = Depends(get_current_user),
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentRunResponse:
    value = await runtime.reject(owner_id=user.id, approval_id=approval_id)
    if value.run.id != run_id:
        from app.domain.base.exceptions import ApplicationError, ErrorCode

        raise ApplicationError(
            "Approval does not belong to Run", error_code=ErrorCode.ENTITY_NOT_FOUND
        )
    return AgentRunResponse.from_view(value)


@router.delete("/{run_id}/checkpoint", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_checkpoint(
    run_id: UUID,
    user: User = Depends(get_current_user),
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> Response:
    await runtime.clear_checkpoints(owner_id=user.id, run_id=run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ("router",)
