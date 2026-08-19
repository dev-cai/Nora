"""Add immutable interview preparation plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_interview_preparations"
down_revision: str | None = "0024_knowledge_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_preparations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("interview_case_id", sa.Uuid(), nullable=False),
        sa.Column("interview_case_version", sa.Integer(), nullable=False),
        sa.Column("application_record_id", sa.Uuid(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("decision_report_id", sa.Uuid(), nullable=True),
        sa.Column("decision_report_version", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("generation_identity", sa.String(64), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_interview_preparation_version"),
        sa.CheckConstraint(
            "interview_case_version >= 1",
            name="ck_interview_preparation_case_version",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_case_id", "interview_case_version", "owner_id"],
            ["interview_cases.id", "interview_cases.version", "interview_cases.owner_id"],
            name="fk_interview_preparation_case_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "interview_case_id",
            "version",
            name="uq_interview_preparation_version",
        ),
    )
    op.create_index("ix_interview_preparations_owner_id", "interview_preparations", ["owner_id"])
    op.create_index(
        "ix_interview_preparations_interview_case_id",
        "interview_preparations",
        ["interview_case_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_preparations_interview_case_id",
        table_name="interview_preparations",
    )
    op.drop_index("ix_interview_preparations_owner_id", table_name="interview_preparations")
    op.drop_table("interview_preparations")
