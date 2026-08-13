"""Add Artifact and SourceDocument lifecycle storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_artifacts_sources"
down_revision: str | None = "0013_application_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=True),
        sa.Column("generation_identity", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_artifact_version"),
        sa.CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_artifact_sha256"),
        sa.CheckConstraint("kind IN ('source', 'generated')", name="ck_artifact_kind"),
        sa.CheckConstraint(
            "(kind = 'generated' AND generator_version IS NOT NULL AND "
            "generation_identity IS NOT NULL) OR "
            "(kind = 'source' AND generator_version IS NULL AND generation_identity IS NULL)",
            name="ck_artifact_generation_identity",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'available', 'failed', "
            "'delete_pending', 'delete_failed', 'deleted')",
            name="ck_artifact_status",
        ),
        sa.CheckConstraint(
            "(status = 'deleted' AND object_key IS NULL AND deleted_at IS NOT NULL) OR "
            "(status <> 'deleted' AND deleted_at IS NULL)",
            name="ck_artifact_tombstone",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_artifact_id_version_owner"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_artifact_owner_key"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_artifacts_owner_id", "artifacts", ["owner_id"], unique=False)
    op.create_index("ix_artifacts_status", "artifacts", ["status"], unique=False)
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("acquisition_method", sa.String(length=100), nullable=False),
        sa.Column("license_note", sa.String(length=500), nullable=False),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_source_version"),
        sa.CheckConstraint("source_kind IN ('file', 'web', 'manual')", name="ck_source_kind"),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_source_sha256"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_source_artifact_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_source_id_version_owner"),
    )
    op.create_index("ix_source_documents_owner_id", "source_documents", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_source_documents_owner_id", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("ix_artifacts_status", table_name="artifacts")
    op.drop_index("ix_artifacts_owner_id", table_name="artifacts")
    op.drop_table("artifacts")
