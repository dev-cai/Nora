"""Add deterministic Resume PDF generation records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_resume_pdfs"
down_revision: str | None = "0016_resume_variants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_pdfs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resume_variant_id", sa.Uuid(), nullable=False),
        sa.Column("resume_variant_version", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("template_definition_hash", sa.String(length=64), nullable=False),
        sa.Column("variant_content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("renderer_version", sa.String(length=100), nullable=False),
        sa.Column("font_set_version", sa.String(length=100), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("generation_identity", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_version", sa.Integer(), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=True),
        sa.Column("pdf_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pdf_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_resume_pdf_version"),
        sa.CheckConstraint("resume_variant_version >= 1", name="ck_resume_pdf_variant_version"),
        sa.CheckConstraint("template_version >= 1", name="ck_resume_pdf_template_version"),
        sa.CheckConstraint(
            "length(template_definition_hash) = 64",
            name="ck_resume_pdf_template_hash",
        ),
        sa.CheckConstraint(
            "length(variant_content_fingerprint) = 64",
            name="ck_resume_pdf_variant_fingerprint",
        ),
        sa.CheckConstraint(
            "length(generation_identity) = 64",
            name="ck_resume_pdf_generation_identity",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'available', 'failed')",
            name="ck_resume_pdf_status",
        ),
        sa.CheckConstraint(
            "(status = 'available' AND artifact_id IS NOT NULL "
            "AND artifact_version IS NOT NULL AND artifact_version >= 1 "
            "AND artifact_sha256 IS NOT NULL AND length(artifact_sha256) = 64 "
            "AND artifact_size_bytes IS NOT NULL AND artifact_size_bytes > 0) OR "
            "(status <> 'available' AND artifact_id IS NULL "
            "AND artifact_version IS NULL AND artifact_sha256 IS NULL "
            "AND artifact_size_bytes IS NULL)",
            name="ck_resume_pdf_artifact_state",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_resume_pdf_variant_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["template_definitions.template_id", "template_definitions.version"],
            name="fk_resume_pdf_template",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_resume_pdf_artifact_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_resume_pdf_identity"),
        sa.UniqueConstraint(
            "owner_id",
            "generation_identity",
            name="uq_resume_pdf_owner_generation",
        ),
    )
    op.create_index("ix_resume_pdfs_owner_id", "resume_pdfs", ["owner_id"], unique=False)
    op.create_index(
        "ix_resume_pdfs_variant",
        "resume_pdfs",
        ["owner_id", "resume_variant_id", "pdf_created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_resume_pdfs_variant", table_name="resume_pdfs")
    op.drop_index("ix_resume_pdfs_owner_id", table_name="resume_pdfs")
    op.drop_table("resume_pdfs")
