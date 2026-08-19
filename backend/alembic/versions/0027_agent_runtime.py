"""Add user-scoped Agent Runtime facts and PostgreSQL checkpoints."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_agent_runtime"
down_revision: str | None = "0026_interview_reviews_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned_table(name: str, columns: list[sa.Column[object]], *constraints: object) -> None:
    op.create_table(
        name,
        *columns,
        *constraints,
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_{name}_owner_id", name, ["owner_id"])


def upgrade() -> None:
    _owned_table(
        "agent_runs",
        [
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("user_goal", sa.Text(), nullable=False),
            sa.Column("thread_id", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("next_action", sa.String(length=100), nullable=True),
            sa.Column("stop_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ],
        sa.UniqueConstraint("thread_id", name="uq_agent_runs_thread_id"),
        sa.CheckConstraint(
            "status IN ('running', 'waiting_approval', 'completed', 'rejected', 'failed')",
            name="ck_agent_runs_status",
        ),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_owner_created", "agent_runs", ["owner_id", "created_at"])

    _owned_table(
        "agent_tool_calls",
        [
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("tool_name", sa.String(length=100), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("result_ref", sa.String(length=255), nullable=True),
            sa.Column("result_summary", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        ],
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('read', 'compute', 'write')", name="ck_agent_tool_kind"),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed')", name="ck_agent_tool_status"
        ),
        sa.CheckConstraint("length(input_fingerprint) = 64", name="ck_agent_tool_fingerprint"),
    )
    op.create_index("ix_agent_tool_calls_run_created", "agent_tool_calls", ["run_id", "created_at"])

    _owned_table(
        "agent_approvals",
        [
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("tool_call_id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("target_type", sa.String(length=100), nullable=False),
            sa.Column("target_id", sa.Uuid(), nullable=True),
            sa.Column("target_version", sa.Integer(), nullable=True),
            sa.Column("action_summary", sa.Text(), nullable=False),
            sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        ],
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["agent_tool_calls.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'consumed')",
            name="ck_agent_approval_status",
        ),
        sa.CheckConstraint("length(input_fingerprint) = 64", name="ck_agent_approval_fingerprint"),
        sa.UniqueConstraint("tool_call_id", name="uq_agent_approval_tool_call"),
    )
    op.create_index("ix_agent_approvals_status", "agent_approvals", ["status"])
    op.create_index("ix_agent_approvals_run_status", "agent_approvals", ["run_id", "status"])

    _owned_table(
        "agent_checkpoints",
        [
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("step", sa.String(length=100), nullable=False),
            sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("next_action", sa.String(length=100), nullable=True),
            sa.Column("stop_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ],
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_agent_checkpoints_run_created", "agent_checkpoints", ["run_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_checkpoints_run_created", table_name="agent_checkpoints")
    op.drop_table("agent_checkpoints")
    op.drop_index("ix_agent_approvals_run_status", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_status", table_name="agent_approvals")
    op.drop_table("agent_approvals")
    op.drop_index("ix_agent_tool_calls_run_created", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
    op.drop_index("ix_agent_runs_owner_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_table("agent_runs")
