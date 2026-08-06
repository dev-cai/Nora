"""Add immutable JobRequirementSnapshot versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_job_requirement_snapshots"
down_revision: str | None = "0009_resume_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_requirement_snapshots",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_job_requirement_version_positive"),
        sa.CheckConstraint(
            "job_posting_version >= 1", name="ck_job_requirement_posting_version_positive"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object' AND content <> '{}'::jsonb",
            name="ck_job_requirement_content_nonempty",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "owner_id",
            "job_posting_id",
            "version",
            name="uq_job_requirement_owner_posting_version",
        ),
    )
    op.create_index(
        "ix_job_requirement_snapshots_owner_id",
        "job_requirement_snapshots",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_requirement_snapshots_job_posting_id",
        "job_requirement_snapshots",
        ["job_posting_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_requirement_snapshots_job_posting_id",
        table_name="job_requirement_snapshots",
    )
    op.drop_index(
        "ix_job_requirement_snapshots_owner_id",
        table_name="job_requirement_snapshots",
    )
    op.drop_table("job_requirement_snapshots")
