"""Add immutable AI job-fit analysis versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_job_fit_analyses"
down_revision: str | None = "0022_interview_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_fit_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("generation_identity", sa.String(length=64), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_job_fit_analysis_version"),
        sa.CheckConstraint(
            "length(generation_identity) = 64",
            name="ck_job_fit_analysis_generation_identity",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_job_fit_analysis_report_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "report_id",
            "version",
            name="uq_job_fit_analysis_report_version",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "generation_identity",
            name="uq_job_fit_analysis_generation",
        ),
    )
    op.create_index("ix_job_fit_analyses_owner_id", "job_fit_analyses", ["owner_id"], unique=False)
    op.create_index(
        "ix_job_fit_analyses_report_id", "job_fit_analyses", ["report_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_job_fit_analyses_report_id", table_name="job_fit_analyses")
    op.drop_index("ix_job_fit_analyses_owner_id", table_name="job_fit_analyses")
    op.drop_table("job_fit_analyses")
