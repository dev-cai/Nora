"""Add user-owned job posting snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_postings"
down_revision: str | None = "0002_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("job_title", sa.String(length=200), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text_summary", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint("length(trim(jd_text)) > 0", name="ck_job_postings_jd_text_nonempty"),
        sa.CheckConstraint("length(jd_text) <= 100000", name="ck_job_postings_jd_text_max_length"),
        sa.CheckConstraint("source_type IN ('manual', 'url')", name="ck_job_postings_source_type"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_job_postings_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_postings_owner_id", "job_postings", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_postings_owner_id", table_name="job_postings")
    op.drop_table("job_postings")
