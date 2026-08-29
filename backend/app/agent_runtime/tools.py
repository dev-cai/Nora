"""固定、typed 的 Agent Tool 注册表。

LangGraph 只能看到这里声明的 DTO 和 Application-facing handlers，不能接触 ORM、Session 或 SDK。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.agent_runtime import AgentToolKind


class AgentToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_goal: str = Field(min_length=1, max_length=4_000)
    interview_case_id: UUID | None = None
    source_id: UUID | None = None
    application_record_id: UUID | None = None
    job_posting_id: UUID | None = None


class AgentToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_ref: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=4_000)
    target_type: str = Field(min_length=1, max_length=100)
    target_id: UUID | None = None
    target_version: int | None = Field(default=None, ge=1)
    payload: dict[str, object] = Field(default_factory=dict)


class AgentToolHandler(Protocol):
    async def __call__(self, value: AgentToolInput) -> AgentToolOutput: ...


@dataclass(frozen=True, slots=True)
class AgentToolSpec:
    name: str
    kind: AgentToolKind
    description: str
    handler: AgentToolHandler


def select_tools(user_goal: str) -> tuple[str, ...]:
    """Deterministic goal router used as the first graph node and easy to audit."""

    goal = user_goal.casefold()
    if any(token in goal for token in ("面试", "interview", "准备")):
        return ("get_opportunity_context", "retrieve_knowledge", "prepare_interview")
    if any(token in goal for token in ("匹配", "适合", "job fit", "岗位分析", "人岗")):
        return ("get_opportunity_context", "analyze_job_fit")
    if any(token in goal for token in ("投递", "申请", "application", "状态")):
        return ("get_application_status",)
    return ("get_opportunity_context", "retrieve_knowledge")


def build_tool_registry(handlers: Mapping[str, AgentToolHandler]) -> Mapping[str, AgentToolSpec]:
    """Build only the fixed registry; unknown runtime names are rejected."""

    definitions = (
        (
            "get_opportunity_context",
            AgentToolKind.READ,
            "读取用户确认的岗位、决策案例和投递上下文",
        ),
        (
            "analyze_job_fit",
            AgentToolKind.COMPUTE,
            "计算人岗匹配分析（当前仅验证 Runtime contract，不接入 JobFit Use Case）",
        ),
        ("retrieve_knowledge", AgentToolKind.READ, "检索用户范围内的版本化知识证据"),
        ("prepare_interview", AgentToolKind.WRITE, "生成版本化面试准备计划"),
        ("get_application_status", AgentToolKind.READ, "读取投递记录及当前状态"),
    )
    missing = [name for name, _, _ in definitions if name not in handlers]
    if missing:
        raise ValueError(f"Missing fixed Agent Tool handler(s): {', '.join(missing)}")
    return MappingProxyType(
        {
            name: AgentToolSpec(name, kind, description, handlers[name])
            for name, kind, description in definitions
        }
    )


def validate_tool_name(registry: Mapping[str, AgentToolSpec], name: str) -> AgentToolSpec:
    try:
        return registry[name]
    except KeyError as exc:
        raise ValueError(f"Unknown Agent Tool: {name}") from exc


__all__ = (
    "AgentToolHandler",
    "AgentToolInput",
    "AgentToolOutput",
    "AgentToolSpec",
    "build_tool_registry",
    "select_tools",
    "validate_tool_name",
)
