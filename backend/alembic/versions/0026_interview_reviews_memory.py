"""Add versioned interview reviews and confirmation-safe memory candidates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_interview_reviews_memory"
down_revision: str | None = "0025_interview_preparations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("interview_case_id", sa.Uuid(), nullable=False),
        sa.Column("interview_case_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_interview_review_version"),
        sa.CheckConstraint("interview_case_version >= 1", name="ck_interview_review_case_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_case_id", "interview_case_version", "owner_id"],
            ["interview_cases.id", "interview_cases.version", "interview_cases.owner_id"],
            name="fk_interview_review_case_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "interview_case_id", "version", name="uq_interview_review_version"
        ),
    )
    op.create_index("ix_interview_reviews_owner_id", "interview_reviews", ["owner_id"])
    op.create_index(
        "ix_interview_reviews_interview_case_id", "interview_reviews", ["interview_case_id"]
    )
    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("review_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("unknown", sa.Boolean(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("review_version >= 1", name="ck_memory_candidate_review_version"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_memory_candidate_confidence",
        ),
        sa.CheckConstraint(
            "kind IN ('skill_gap', 'interview_pattern', 'resume_issue', 'knowledge_gap')",
            name="ck_memory_candidate_kind",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'revoked')",
            name="ck_memory_candidate_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["interview_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_candidates_owner_id", "memory_candidates", ["owner_id"])
    op.create_index("ix_memory_candidates_review_id", "memory_candidates", ["review_id"])
    op.create_index("ix_memory_candidates_status", "memory_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_memory_candidates_status", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_review_id", table_name="memory_candidates")
    op.drop_index("ix_memory_candidates_owner_id", table_name="memory_candidates")
    op.drop_table("memory_candidates")
    op.drop_index("ix_interview_reviews_interview_case_id", table_name="interview_reviews")
    op.drop_index("ix_interview_reviews_owner_id", table_name="interview_reviews")
    op.drop_table("interview_reviews")
