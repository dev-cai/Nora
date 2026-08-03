"""Add immutable CandidateProfile versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_candidate_profile_versions"
down_revision: str | None = "0007_job_posting_public_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profile_versions",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_candidate_profile_version_positive"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("owner_id", "version", name="uq_candidate_profile_owner_version"),
    )
    op.create_index(
        "ix_candidate_profile_versions_owner_id",
        "candidate_profile_versions",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_profile_versions_owner_id",
        table_name="candidate_profile_versions",
    )
    op.drop_table("candidate_profile_versions")
