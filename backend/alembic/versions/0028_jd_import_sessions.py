"""Add user-scoped JD ImportSession and ImportDraft candidates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_jd_import_sessions"
down_revision: str | None = "0027_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("import_type", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_draft_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_job_posting_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_requirement_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("import_type IN ('jd')", name="ck_import_sessions_type"),
        sa.CheckConstraint(
            "source_type IN ('text', 'image', 'url')", name="ck_import_sessions_source_type"
        ),
        sa.CheckConstraint(
            "status IN ('created', 'draft_ready', 'failed', 'confirmed')",
            name="ck_import_sessions_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_sessions_owner_id", "import_sessions", ["owner_id"])
    op.create_index("ix_import_sessions_status", "import_sessions", ["status"])
    op.create_table(
        "import_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("import_type", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("import_type IN ('jd')", name="ck_import_drafts_type"),
        sa.CheckConstraint("version >= 1", name="ck_import_drafts_version"),
        sa.CheckConstraint("length(content_fingerprint) = 64", name="ck_import_drafts_fingerprint"),
        sa.ForeignKeyConstraint(["session_id"], ["import_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_drafts_session_id", "import_drafts", ["session_id"])
    op.create_index("ix_import_drafts_owner_id", "import_drafts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_import_drafts_owner_id", table_name="import_drafts")
    op.drop_index("ix_import_drafts_session_id", table_name="import_drafts")
    op.drop_table("import_drafts")
    op.drop_index("ix_import_sessions_status", table_name="import_sessions")
    op.drop_index("ix_import_sessions_owner_id", table_name="import_sessions")
    op.drop_table("import_sessions")
