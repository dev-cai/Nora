"""Add versioned user-confirmed interview notification facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_interview_cases"
down_revision: str | None = "0021_beta_auth_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_cases",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("application_record_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("meeting_url", sa.Text(), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("case_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_interview_case_version"),
        sa.CheckConstraint("actor_id = owner_id", name="ck_interview_case_actor_owner"),
        sa.CheckConstraint(
            "mode IN ('onsite', 'online', 'phone')", name="ck_interview_case_mode"
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'cancelled')", name="ck_interview_case_status"
        ),
        sa.CheckConstraint("source = 'user_confirmation'", name="ck_interview_case_source"),
        sa.CheckConstraint(
            "round_number BETWEEN 1 AND 20", name="ck_interview_case_round"
        ),
        sa.CheckConstraint(
            "(mode = 'onsite' AND location IS NOT NULL AND meeting_url IS NULL) OR "
            "(mode = 'online' AND location IS NULL AND meeting_url IS NOT NULL) OR "
            "(mode = 'phone' AND location IS NULL AND meeting_url IS NULL)",
            name="ck_interview_case_mode_fields",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 255 AND "
            "length(request_fingerprint) = 64",
            name="ck_interview_case_identity",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["application_record_id", "owner_id"],
            ["application_records.id", "application_records.owner_id"],
            name="fk_interview_case_application_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_interview_case_version"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_interview_case_owner_key"),
    )
    op.create_index("ix_interview_cases_id", "interview_cases", ["id"], unique=False)
    op.create_index(
        "ix_interview_cases_owner_id", "interview_cases", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_interview_cases_owner_start",
        "interview_cases",
        ["owner_id", "starts_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interview_cases_owner_start", table_name="interview_cases")
    op.drop_index("ix_interview_cases_owner_id", table_name="interview_cases")
    op.drop_index("ix_interview_cases_id", table_name="interview_cases")
    op.drop_table("interview_cases")
