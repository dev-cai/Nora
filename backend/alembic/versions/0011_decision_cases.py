"""Add immutable DecisionCase inputs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_decision_cases"
down_revision: str | None = "0010_job_requirement_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_job_posting_id_version_owner", "job_postings", ["id", "version", "owner_id"]
    )
    op.create_unique_constraint(
        "uq_job_requirement_snapshot_id_version_owner",
        "job_requirement_snapshots",
        ["snapshot_id", "version", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_candidate_profile_id_version_owner",
        "candidate_profile_versions",
        ["profile_id", "version", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_resume_version_id_version_owner",
        "resume_versions",
        ["id", "version", "owner_id"],
    )
    op.create_table(
        "decision_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_version", sa.Integer(), nullable=False),
        sa.Column("job_requirement_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("job_requirement_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("candidate_profile_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_profile_version", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("rule_set_version", sa.String(length=100), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.CheckConstraint("job_posting_version >= 1", name="ck_decision_job_version_positive"),
        sa.CheckConstraint(
            "job_requirement_snapshot_version >= 1",
            name="ck_decision_requirement_version_positive",
        ),
        sa.CheckConstraint(
            "candidate_profile_version >= 1", name="ck_decision_profile_version_positive"
        ),
        sa.CheckConstraint("resume_version >= 1", name="ck_decision_resume_version_positive"),
        sa.CheckConstraint(
            "status IN ('created', 'completed', 'failed')", name="ck_decision_status"
        ),
        sa.CheckConstraint(
            "(status = 'created' AND completed_at IS NULL AND failure_code IS NULL "
            "AND failure_message IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL AND failure_code IS NULL "
            "AND failure_message IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL AND failure_code IS NOT NULL "
            "AND failure_message IS NOT NULL)",
            name="ck_decision_terminal_state",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "input_fingerprint", name="uq_decision_case_owner_fingerprint"
        ),
    )
    op.create_foreign_key(
        "fk_decision_case_job_input",
        "decision_cases",
        "job_postings",
        ["job_posting_id", "job_posting_version", "owner_id"],
        ["id", "version", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_decision_case_requirement_input",
        "decision_cases",
        "job_requirement_snapshots",
        ["job_requirement_snapshot_id", "job_requirement_snapshot_version", "owner_id"],
        ["snapshot_id", "version", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_decision_case_profile_input",
        "decision_cases",
        "candidate_profile_versions",
        ["candidate_profile_id", "candidate_profile_version", "owner_id"],
        ["profile_id", "version", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_decision_case_resume_input",
        "decision_cases",
        "resume_versions",
        ["resume_version_id", "resume_version", "owner_id"],
        ["id", "version", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_decision_cases_owner_id", "decision_cases", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_decision_cases_owner_id", table_name="decision_cases")
    op.drop_table("decision_cases")
    op.drop_constraint("uq_resume_version_id_version_owner", "resume_versions", type_="unique")
    op.drop_constraint(
        "uq_candidate_profile_id_version_owner",
        "candidate_profile_versions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_job_requirement_snapshot_id_version_owner",
        "job_requirement_snapshots",
        type_="unique",
    )
    op.drop_constraint("uq_job_posting_id_version_owner", "job_postings", type_="unique")
