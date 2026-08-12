"""Add immutable apply/skip decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_application_decisions"
down_revision: str | None = "0012_decision_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_decision_report_id_version_owner",
        "decision_reports",
        ["id", "version", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_decision_report_case_identity",
        "decision_reports",
        ["id", "version", "decision_case_id", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_decision_case_resume_owner",
        "decision_cases",
        ["id", "resume_version_id", "resume_version", "owner_id"],
    )
    op.create_table(
        "application_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "report_version >= 1", name="ck_application_decision_report_version"
        ),
        sa.CheckConstraint(
            "resume_version >= 1", name="ck_application_decision_resume_version"
        ),
        sa.CheckConstraint(
            "status IN ('apply', 'skip')", name="ck_application_decision_status"
        ),
        sa.CheckConstraint(
            "actor_id = owner_id", name="ck_application_decision_actor_owner"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 255",
            name="ck_application_decision_key_length",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_application_decision_fingerprint_length",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR length(reason) <= 1000",
            name="ck_application_decision_reason_length",
        ),
        sa.CheckConstraint(
            "(status = 'skip' AND reason IS NOT NULL AND length(trim(reason)) > 0) OR "
            "(status = 'apply')",
            name="ck_application_decision_skip_reason",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_application_decision_report_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_case_id", "resume_version_id", "resume_version", "owner_id"],
            [
                "decision_cases.id",
                "decision_cases.resume_version_id",
                "decision_cases.resume_version",
                "decision_cases.owner_id",
            ],
            name="fk_application_decision_case_resume_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_application_decision_resume_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "report_id", name="uq_application_decision_owner_report"
        ),
        sa.UniqueConstraint(
            "owner_id", "idempotency_key", name="uq_application_decision_owner_key"
        ),
    )
    op.create_index(
        "ix_application_decisions_owner_id",
        "application_decisions",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_decisions_owner_id", table_name="application_decisions")
    op.drop_table("application_decisions")
    op.drop_constraint(
        "uq_decision_case_resume_owner", "decision_cases", type_="unique"
    )
    op.drop_constraint(
        "uq_decision_report_case_identity", "decision_reports", type_="unique"
    )
    op.drop_constraint(
        "uq_decision_report_id_version_owner", "decision_reports", type_="unique"
    )
