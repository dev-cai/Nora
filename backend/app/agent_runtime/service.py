"""Single Agent/single Graph adapter with explicit approval and recovery boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict
from uuid import UUID

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.domain.agent_runtime import (
    AgentApproval,
    AgentApprovalStatus,
    AgentCheckpoint,
    AgentRun,
    AgentRunStatus,
    AgentToolCall,
    AgentToolKind,
)
from app.domain.base.exceptions import ApplicationError, ErrorCode
from app.ports.agent_runtime import AgentRuntimeRepository

from .tools import AgentToolInput, AgentToolOutput, AgentToolSpec, select_tools, validate_tool_name


class RuntimeState(TypedDict, total=False):
    user_goal: str
    selected_tools: list[str]
    current_index: int
    pending_tool: str | None
    pending_tool_call_id: str | None
    pending_approval_id: str | None
    results: list[dict[str, object]]
    next_action: str | None
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class AgentRunView:
    run: AgentRun
    tool_calls: tuple[AgentToolCall, ...]
    approval: AgentApproval | None
    checkpoint: AgentCheckpoint | None


class AgentRuntimeService:
    """Owns LangGraph execution while application facts remain behind typed handlers."""

    def __init__(
        self,
        repository: AgentRuntimeRepository,
        registry: dict[str, AgentToolSpec],
        *,
        checkpoint_database_url: str | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.checkpoint_database_url = checkpoint_database_url
        self._graphs: dict[UUID, Any] = {}
        self._checkpoint_contexts: dict[UUID, Any] = {}

    async def start(
        self, *, owner_id: UUID, user_goal: str, tool_input: AgentToolInput
    ) -> AgentRunView:
        run = AgentRun.create(owner_id=owner_id, user_goal=user_goal)
        await self.repository.add_run(run)
        await self.repository.commit()
        graph = await self._build_graph(run, tool_input)
        self._graphs[run.id] = graph
        await self._invoke(run, graph, {"user_goal": run.user_goal}, resume=None)
        return await self.view(owner_id=owner_id, run_id=run.id)

    async def approve(self, *, owner_id: UUID, approval_id: UUID) -> AgentRunView:
        approval = await self.repository.get_approval(approval_id)
        if approval is None or approval.owner_id != owner_id:
            raise ApplicationError("Approval not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        if approval.status is not AgentApprovalStatus.PENDING:
            return await self.view(owner_id=owner_id, run_id=approval.run_id)
        decided = approval.decide(AgentApprovalStatus.APPROVED)
        await self.repository.update_approval(decided)
        run = await self._require_run(owner_id, approval.run_id)
        await self.repository.update_run(
            run.transition(AgentRunStatus.RUNNING, next_action="resume")
        )
        await self.repository.commit()
        graph = self._graphs.get(run.id)
        if graph is None:
            checkpoint = await self.repository.get_latest_checkpoint(run.id)
            if checkpoint is None:
                raise ApplicationError(
                    "Agent checkpoint is unavailable",
                    error_code=ErrorCode.MODEL_PROVIDER_UNAVAILABLE,
                )
            calls = await self.repository.list_tool_calls(run.id)
            approval_call = next((item for item in calls if item.id == approval.tool_call_id), None)
            if approval_call is None:
                raise ApplicationError(
                    "Approved ToolCall is unavailable",
                    error_code=ErrorCode.ENTITY_NOT_FOUND,
                )
            graph = await self._build_graph(
                run,
                AgentToolInput.model_validate(approval_call.input_payload),
            )
            self._graphs[run.id] = graph
            await self._invoke(run, graph, checkpoint.state, resume=None)
        else:
            await self._invoke(run, graph, {}, resume={"approved": True})
        return await self.view(owner_id=owner_id, run_id=run.id)

    async def reject(self, *, owner_id: UUID, approval_id: UUID) -> AgentRunView:
        approval = await self.repository.get_approval(approval_id)
        if approval is None or approval.owner_id != owner_id:
            raise LookupError("Approval not found")
        if approval.status is AgentApprovalStatus.PENDING:
            await self.repository.update_approval(approval.decide(AgentApprovalStatus.REJECTED))
            run = await self._require_run(owner_id, approval.run_id)
            await self.repository.update_run(
                run.transition(AgentRunStatus.REJECTED, stop_reason="用户拒绝写入")
            )
            await self.repository.commit()
        return await self.view(owner_id=owner_id, run_id=approval.run_id)

    async def view(self, *, owner_id: UUID, run_id: UUID) -> AgentRunView:
        run = await self._require_run(owner_id, run_id)
        return AgentRunView(
            run,
            tuple(await self.repository.list_tool_calls(run_id)),
            await self.repository.get_pending_approval(run_id),
            await self.repository.get_latest_checkpoint(run_id),
        )

    async def clear_checkpoints(self, *, owner_id: UUID, run_id: UUID) -> None:
        await self._require_run(owner_id, run_id)
        await self.repository.delete_checkpoints(run_id)
        await self.repository.commit()

    async def _invoke(
        self,
        run: AgentRun,
        graph: Any,
        values: dict[str, object],
        *,
        resume: dict[str, object] | None,
    ) -> None:
        config = {"configurable": {"thread_id": run.thread_id}}
        result = await graph.ainvoke(
            Command(resume=resume) if resume is not None else values, config
        )
        state = graph.get_state(config)
        state_values = dict(state.values)
        await self.repository.add_checkpoint(
            AgentCheckpoint.save(
                run_id=run.id,
                owner_id=run.owner_id,
                step=state.next[0] if state.next else "complete",
                state=_safe_state(state_values),
                next_action=state_values.get("next_action"),
                stop_reason=state_values.get("stop_reason"),
            )
        )
        if "__interrupt__" in result:
            await self.repository.commit()
            return
        current = await self._require_run(run.owner_id, run.id)
        final_status = (
            AgentRunStatus.REJECTED if state_values.get("stop_reason") else AgentRunStatus.COMPLETED
        )
        await self.repository.update_run(
            current.transition(
                final_status,
                next_action=None,
                stop_reason=state_values.get("stop_reason"),
            )
        )
        await self.repository.commit()

    async def _build_graph(self, run: AgentRun, tool_input: AgentToolInput) -> Any:
        service = self

        async def route(state: RuntimeState) -> RuntimeState:
            selected = list(select_tools(state["user_goal"]))
            for name in selected:
                validate_tool_name(service.registry, name)
            return {"selected_tools": selected, "current_index": 0, "next_action": selected[0]}

        async def execute(state: RuntimeState) -> RuntimeState:
            selected = state["selected_tools"]
            index = state.get("current_index", 0)
            if index >= len(selected):
                return {"next_action": None}
            name = selected[index]
            spec = validate_tool_name(service.registry, name)
            payload = tool_input.model_copy(update={"user_goal": state["user_goal"]})
            pending_id = state.get("pending_tool_call_id")
            existing_approval = await service.repository.get_latest_approval(run.id)
            existing_calls = await service.repository.list_tool_calls(run.id)
            existing_call = next(
                (
                    item
                    for item in existing_calls
                    if existing_approval and item.id == existing_approval.tool_call_id
                ),
                None,
            )
            if spec.kind is AgentToolKind.WRITE and existing_approval is None and not pending_id:
                call = AgentToolCall.start(
                    run_id=run.id,
                    owner_id=run.owner_id,
                    tool_name=name,
                    kind=spec.kind,
                    input_payload=payload.model_dump(mode="json"),
                )
                await service.repository.add_tool_call(call)
                output = AgentToolOutput(
                    result_ref=f"agent-approval:{call.id}",
                    summary=f"{spec.description}（需用户确认）",
                    target_type=spec.name,
                    payload=payload.model_dump(mode="json"),
                )
                approval = AgentApproval.pending(
                    run_id=run.id,
                    tool_call_id=call.id,
                    owner_id=run.owner_id,
                    target_type=output.target_type,
                    target_id=output.target_id,
                    target_version=output.target_version,
                    action_summary=output.summary,
                    input_fingerprint=call.input_fingerprint,
                )
                await service.repository.add_approval(approval)
                await service.repository.update_run(
                    run.transition(AgentRunStatus.WAITING_APPROVAL, next_action="approval")
                )
                decision = interrupt(
                    {
                        "approval_id": str(approval.id),
                        "tool_name": name,
                        "action_summary": output.summary,
                        "target_type": output.target_type,
                        "target_id": str(output.target_id) if output.target_id else None,
                        "target_version": output.target_version,
                    }
                )
                if not decision.get("approved"):
                    return {"stop_reason": "用户拒绝写入", "next_action": None}
                await service.repository.update_approval(
                    approval.decide(AgentApprovalStatus.APPROVED).consume()
                )
                pending_id = str(call.id)
                result = await spec.handler(payload)
            elif spec.kind is AgentToolKind.WRITE and existing_approval is not None:
                if existing_approval.status is AgentApprovalStatus.PENDING:
                    decision = interrupt(
                        {
                            "approval_id": str(existing_approval.id),
                            "tool_name": name,
                            "action_summary": existing_approval.action_summary,
                            "target_type": existing_approval.target_type,
                            "target_id": str(existing_approval.target_id)
                            if existing_approval.target_id
                            else None,
                            "target_version": existing_approval.target_version,
                        }
                    )
                    if not decision.get("approved"):
                        return {"stop_reason": "用户拒绝写入", "next_action": None}
                    await service.repository.update_approval(
                        existing_approval.decide(AgentApprovalStatus.APPROVED).consume()
                    )
                if existing_call is None:
                    raise RuntimeError("Approved Agent ToolCall is missing")
                call = existing_call
                if existing_approval.status is AgentApprovalStatus.APPROVED:
                    await service.repository.update_approval(existing_approval.consume())
                result = await spec.handler(payload)
            else:
                result = await spec.handler(payload)
                call = AgentToolCall.start(
                    run_id=run.id,
                    owner_id=run.owner_id,
                    tool_name=name,
                    kind=spec.kind,
                    input_payload=payload.model_dump(mode="json"),
                )
                await service.repository.add_tool_call(call)
            call_result = call.succeed(result_ref=result.result_ref, result_summary=result.summary)
            await service.repository.update_tool_call(call_result)
            next_index = index + 1
            return {
                "current_index": next_index,
                "pending_tool_call_id": None,
                "pending_approval_id": None,
                "results": [*state.get("results", []), result.model_dump(mode="json")],
                "next_action": selected[next_index] if next_index < len(selected) else None,
            }

        graph = StateGraph(RuntimeState)
        graph.add_node("route_goal", route)
        graph.add_node("execute_tool", execute)
        graph.add_edge(START, "route_goal")
        graph.add_edge("route_goal", "execute_tool")
        graph.add_conditional_edges(
            "execute_tool",
            lambda state: "execute_tool" if state.get("next_action") else END,
        )
        saver: Any
        if self.checkpoint_database_url:
            connection_string = self.checkpoint_database_url.replace("+asyncpg", "", 1)
            context = AsyncPostgresSaver.from_conn_string(connection_string)
            saver = await context.__aenter__()
            await saver.setup()
            self._checkpoint_contexts[run.id] = context
        else:
            saver = InMemorySaver()
        return graph.compile(checkpointer=saver)

    async def _require_run(self, owner_id: UUID, run_id: UUID) -> AgentRun:
        run = await self.repository.get_run(run_id)
        if run is None or run.owner_id != owner_id:
            raise ApplicationError("Agent Run not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return run


def _safe_state(state: dict[str, object]) -> dict[str, object]:
    allowed = {
        "user_goal",
        "selected_tools",
        "current_index",
        "results",
        "next_action",
        "stop_reason",
    }
    return {key: value for key, value in state.items() if key in allowed}


__all__ = ("AgentRuntimeService", "AgentRunView")
