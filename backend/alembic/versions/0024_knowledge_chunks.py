"""Add rebuildable source chunks and embeddings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_knowledge_chunks"
down_revision: str | None = "0023_job_fit_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding_version", sa.String(100), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_chunk_ordinal"),
        sa.CheckConstraint("embedding_dimension > 0", name="ck_chunk_embedding_dimension"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_id", "source_version", "owner_id"],
            ["source_documents.id", "source_documents.version", "source_documents.owner_id"],
            name="fk_chunk_source_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "source_id",
            "source_version",
            "ordinal",
            name="uq_chunk_source_ordinal",
        ),
    )
    op.create_index("ix_knowledge_chunks_owner_id", "knowledge_chunks", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_owner_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
