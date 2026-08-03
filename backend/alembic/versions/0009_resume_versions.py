"""Add immutable ResumeVersion snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_resume_versions"
down_revision: str | None = "0008_candidate_profile_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_candidate_profile_id_version",
        "candidate_profile_versions",
        ["profile_id", "version"],
    )
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("candidate_profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_resume_version_version_positive"),
        sa.CheckConstraint("profile_version >= 1", name="ck_resume_version_profile_positive"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_resume_version_title_nonempty"),
        sa.CheckConstraint("length(title) <= 200", name="ck_resume_version_title_max_length"),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object' AND content <> '{}'::jsonb",
            name="ck_resume_version_content_nonempty",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id", "profile_version"],
            ["candidate_profile_versions.profile_id", "candidate_profile_versions.version"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "version", name="uq_resume_version_owner_version"),
    )
    op.create_index("ix_resume_versions_owner_id", "resume_versions", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_resume_versions_owner_id", table_name="resume_versions")
    op.drop_table("resume_versions")
    op.drop_constraint(
        "uq_candidate_profile_id_version",
        "candidate_profile_versions",
        type_="unique",
    )
