"""Add immutable versioned DecisionReport storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_decision_reports"
down_revision: str | None = "0011_decision_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_decision_case_id_owner", "decision_cases", ["id", "owner_id"])
    op.create_table(
        "decision_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rule_set_version", sa.String(length=100), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_decision_report_version_positive"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_case_id", "owner_id"],
            ["decision_cases.id", "decision_cases.owner_id"],
            name="fk_decision_report_case_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_case_id", "version", name="uq_decision_report_case_version"),
        sa.UniqueConstraint(
            "owner_id",
            "decision_case_id",
            "rule_set_version",
            "generator_version",
            name="uq_decision_report_generation",
        ),
    )
    op.create_index("ix_decision_reports_owner_id", "decision_reports", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_decision_reports_owner_id", table_name="decision_reports")
    op.drop_table("decision_reports")
    op.drop_constraint("uq_decision_case_id_owner", "decision_cases", type_="unique")
