"""Single-agent graph, fixed Tool Registry and approval boundary tests."""

from uuid import UUID, uuid4

import pytest
from app.agent_runtime import AgentRuntimeService
from app.agent_runtime.tools import (
    AgentToolInput,
    AgentToolOutput,
    build_tool_registry,
    select_tools,
    validate_tool_name,
)
from app.domain.agent_runtime import (
    AgentApproval,
    AgentCheckpoint,
    AgentRun,
    AgentRunStatus,
    AgentToolCall,
    AgentToolKind,
)
from app.domain.base.exceptions import ApplicationError, ErrorCode


class FakeRuntimeRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, AgentRun] = {}
        self.calls: dict[UUID, AgentToolCall] = {}
        self.approvals: dict[UUID, AgentApproval] = {}
        self.checkpoints: dict[UUID, AgentCheckpoint] = {}
        self.business_writes = 0

    async def add_run(self, run: AgentRun) -> AgentRun:
        self.runs[run.id] = run
        return run

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        return self.runs.get(run_id)

    async def update_run(self, run: AgentRun) -> AgentRun:
        self.runs[run.id] = run
        return run

    async def add_tool_call(self, call: AgentToolCall) -> AgentToolCall:
        self.calls[call.id] = call
        return call

    async def update_tool_call(self, call: AgentToolCall) -> AgentToolCall:
        self.calls[call.id] = call
        return call

    async def list_tool_calls(self, run_id: UUID) -> list[AgentToolCall]:
        return [value for value in self.calls.values() if value.run_id == run_id]

    async def add_approval(self, approval: AgentApproval) -> AgentApproval:
        self.approvals[approval.id] = approval
        return approval

    async def get_approval(self, approval_id: UUID) -> AgentApproval | None:
        return self.approvals.get(approval_id)

    async def get_pending_approval(self, run_id: UUID) -> AgentApproval | None:
        return next(
            (
                value
                for value in self.approvals.values()
                if value.run_id == run_id and value.status.value == "pending"
            ),
            None,
        )

    async def get_latest_approval(self, run_id: UUID) -> AgentApproval | None:
        values = [value for value in self.approvals.values() if value.run_id == run_id]
        return values[-1] if values else None

    async def update_approval(self, approval: AgentApproval) -> AgentApproval:
        self.approvals[approval.id] = approval
        return approval

    async def add_checkpoint(self, checkpoint: AgentCheckpoint) -> AgentCheckpoint:
        self.checkpoints[checkpoint.run_id] = checkpoint
        return checkpoint

    async def get_latest_checkpoint(self, run_id: UUID) -> AgentCheckpoint | None:
        return self.checkpoints.get(run_id)

    async def delete_checkpoints(self, run_id: UUID) -> None:
        self.checkpoints.pop(run_id, None)

    async def commit(self) -> None:
        return None


def _handlers(repository: FakeRuntimeRepository):
    async def read(value: AgentToolInput) -> AgentToolOutput:
        return AgentToolOutput(
            result_ref="read:1",
            summary=value.user_goal,
            target_type="context",
            payload={"goal": value.user_goal},
        )

    async def write(value: AgentToolInput) -> AgentToolOutput:
        repository.business_writes += 1
        return AgentToolOutput(
            result_ref="write:1",
            summary="写入已完成",
            target_type="existing_use_case",
            target_id=value.interview_case_id,
            target_version=1,
        )

    async def compute(value: AgentToolInput) -> AgentToolOutput:
        return AgentToolOutput(
            result_ref="compute:1",
            summary="计算完成",
            target_type="compute_result",
            payload={"goal": value.user_goal},
        )

    return {
        "get_opportunity_context": read,
        "analyze_job_fit": compute,
        "retrieve_knowledge": read,
        "prepare_interview": write,
        "get_application_status": read,
    }


def test_goal_router_is_temporary_generic_runtime_routing() -> None:
    assert select_tools("帮我准备面试") == (
        "get_opportunity_context",
        "retrieve_knowledge",
        "prepare_interview",
    )
    assert select_tools("分析这个岗位是否适合我") == (
        "get_opportunity_context",
        "analyze_job_fit",
    )
    assert select_tools("查看我的投递状态") == ("get_application_status",)


def test_registry_rejects_unknown_tool() -> None:
    repository = FakeRuntimeRepository()
    registry = build_tool_registry(_handlers(repository))
    with pytest.raises(ValueError, match="Unknown Agent Tool"):
        validate_tool_name(registry, "arbitrary_python")


def test_registry_classifies_compute_without_approval() -> None:
    repository = FakeRuntimeRepository()
    registry = build_tool_registry(_handlers(repository))
    assert registry["analyze_job_fit"].kind is AgentToolKind.COMPUTE
    assert registry["prepare_interview"].kind is AgentToolKind.WRITE


@pytest.mark.asyncio
async def test_compute_completes_without_business_write_or_approval() -> None:
    repository = FakeRuntimeRepository()
    service = AgentRuntimeService(repository, dict(build_tool_registry(_handlers(repository))))
    owner_id = uuid4()
    value = await service.start(
        owner_id=owner_id,
        user_goal="分析这个岗位是否适合我",
        tool_input=AgentToolInput(user_goal="分析这个岗位是否适合我", interview_case_id=uuid4()),
    )

    assert value.run.status is AgentRunStatus.COMPLETED
    assert value.approval is None
    assert repository.business_writes == 0


@pytest.mark.asyncio
async def test_decision_entry_uses_explicit_report_anchor_and_fixed_compute_plan() -> None:
    repository = FakeRuntimeRepository()
    seen: list[UUID | None] = []

    async def analyze(value: AgentToolInput) -> AgentToolOutput:
        seen.append(value.report_id)
        return AgentToolOutput(
            result_ref="job-fit-analysis:1:v1",
            summary="已生成人岗分析",
            target_type="job_fit_analysis",
            target_id=uuid4(),
            target_version=1,
        )

    handlers = _handlers(repository)
    handlers["analyze_job_fit"] = analyze
    service = AgentRuntimeService(repository, dict(build_tool_registry(handlers)))
    report_id = uuid4()

    value = await service.start_decision_analysis(owner_id=uuid4(), report_id=report_id)

    assert value.run.status is AgentRunStatus.COMPLETED
    assert [item.tool_name for item in value.tool_calls] == ["analyze_job_fit"]
    assert value.approval is None
    assert seen == [report_id]


@pytest.mark.asyncio
async def test_compute_failure_records_failed_tool_call_and_run() -> None:
    repository = FakeRuntimeRepository()

    async def failing_compute(_value: AgentToolInput) -> AgentToolOutput:
        raise ApplicationError("Model unavailable", error_code=ErrorCode.MODEL_PROVIDER_UNAVAILABLE)

    handlers = _handlers(repository)
    handlers["analyze_job_fit"] = failing_compute
    service = AgentRuntimeService(repository, dict(build_tool_registry(handlers)))

    with pytest.raises(ApplicationError) as exc_info:
        await service.start_decision_analysis(owner_id=uuid4(), report_id=uuid4())

    assert exc_info.value.error_code is ErrorCode.MODEL_PROVIDER_UNAVAILABLE
    run = next(iter(repository.runs.values()))
    calls = await repository.list_tool_calls(run.id)
    assert run.status is AgentRunStatus.FAILED
    assert len(calls) == 1
    assert calls[0].status.value == "failed"
    assert calls[0].error_code == ErrorCode.MODEL_PROVIDER_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_unexpected_compute_failure_records_internal_error_without_exception_text() -> None:
    repository = FakeRuntimeRepository()

    async def failing_compute(_value: AgentToolInput) -> AgentToolOutput:
        raise RuntimeError("provider secret response must not be persisted")

    handlers = _handlers(repository)
    handlers["analyze_job_fit"] = failing_compute
    service = AgentRuntimeService(repository, dict(build_tool_registry(handlers)))

    with pytest.raises(RuntimeError, match="provider secret"):
        await service.start_decision_analysis(owner_id=uuid4(), report_id=uuid4())

    run = next(iter(repository.runs.values()))
    calls = await repository.list_tool_calls(run.id)
    assert run.status is AgentRunStatus.FAILED
    assert calls[0].error_code == ErrorCode.INTERNAL_ERROR.value
    assert "provider secret" not in (run.stop_reason or "")


@pytest.mark.asyncio
async def test_write_interrupts_before_business_write_then_resumes_after_approval() -> None:
    repository = FakeRuntimeRepository()
    service = AgentRuntimeService(repository, dict(build_tool_registry(_handlers(repository))))
    owner_id = uuid4()
    value = await service.start(
        owner_id=owner_id,
        user_goal="帮我准备面试",
        tool_input=AgentToolInput(user_goal="帮我准备面试", interview_case_id=uuid4()),
    )

    assert value.run.status is AgentRunStatus.WAITING_APPROVAL
    assert value.approval is not None
    assert repository.business_writes == 0
    assert len(value.tool_calls) == 3

    resumed = await service.approve(owner_id=owner_id, approval_id=value.approval.id)

    assert resumed.run.status is AgentRunStatus.COMPLETED
    assert resumed.approval is None
    assert repository.business_writes == 1
    assert all(item.result_ref for item in resumed.tool_calls)


@pytest.mark.asyncio
async def test_checkpoint_state_keeps_result_references_only() -> None:
    repository = FakeRuntimeRepository()
    service = AgentRuntimeService(repository, dict(build_tool_registry(_handlers(repository))))
    value = await service.start(
        owner_id=uuid4(),
        user_goal="查找相关知识",
        tool_input=AgentToolInput(user_goal="查找相关知识"),
    )

    checkpoint = await repository.get_latest_checkpoint(value.run.id)
    assert checkpoint is not None
    assert all(isinstance(item, str) for item in checkpoint.state["results"])
    assert all("summary" not in item for item in checkpoint.state["results"])


@pytest.mark.asyncio
async def test_run_and_approval_are_owner_isolated() -> None:
    repository = FakeRuntimeRepository()
    service = AgentRuntimeService(repository, dict(build_tool_registry(_handlers(repository))))
    owner_id = uuid4()
    other_owner_id = uuid4()
    value = await service.start(
        owner_id=owner_id,
        user_goal="帮我准备面试",
        tool_input=AgentToolInput(user_goal="帮我准备面试", interview_case_id=uuid4()),
    )

    with pytest.raises(ApplicationError) as view_error:
        await service.view(owner_id=other_owner_id, run_id=value.run.id)
    assert view_error.value.error_code is ErrorCode.ENTITY_NOT_FOUND
    assert value.approval is not None
    with pytest.raises(ApplicationError) as approve_error:
        await service.approve(owner_id=other_owner_id, approval_id=value.approval.id)
    assert approve_error.value.error_code is ErrorCode.ENTITY_NOT_FOUND


@pytest.mark.asyncio
async def test_reject_ends_run_and_checkpoint_cleanup_keeps_run() -> None:
    repository = FakeRuntimeRepository()
    service = AgentRuntimeService(repository, dict(build_tool_registry(_handlers(repository))))
    owner_id = uuid4()
    value = await service.start(
        owner_id=owner_id,
        user_goal="帮我准备面试",
        tool_input=AgentToolInput(user_goal="帮我准备面试", interview_case_id=uuid4()),
    )
    assert value.approval is not None

    rejected = await service.reject(owner_id=owner_id, approval_id=value.approval.id)
    await service.clear_checkpoints(owner_id=owner_id, run_id=rejected.run.id)

    assert rejected.run.status is AgentRunStatus.REJECTED
    assert repository.business_writes == 0
    assert await repository.get_run(rejected.run.id) is not None
    assert await repository.get_latest_checkpoint(rejected.run.id) is None
