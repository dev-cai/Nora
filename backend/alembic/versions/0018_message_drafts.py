"""Add deterministic, append-only MessageDraft versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_message_drafts"
down_revision: str | None = "0017_resume_pdfs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_drafts",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("application_decision_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("resume_variant_id", sa.Uuid(), nullable=False),
        sa.Column("resume_variant_version", sa.Integer(), nullable=False),
        sa.Column("variant_content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_profile_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_profile_version", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("company_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("company_snapshot_version", sa.Integer(), nullable=True),
        sa.Column("company_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("company_freshness", sa.String(length=32), nullable=True),
        sa.Column("company_industry", sa.String(length=200), nullable=True),
        sa.Column("style", sa.String(length=32), nullable=False),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("referral_context", sa.Text(), nullable=True),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("template_version", sa.String(length=100), nullable=False),
        sa.Column("generation_identity", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision_type", sa.String(length=16), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("draft_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_message_draft_version"),
        sa.CheckConstraint("report_version >= 1", name="ck_message_draft_report_version"),
        sa.CheckConstraint("resume_variant_version >= 1", name="ck_message_draft_variant_version"),
        sa.CheckConstraint(
            "candidate_profile_version >= 1", name="ck_message_draft_profile_version"
        ),
        sa.CheckConstraint("resume_version >= 1", name="ck_message_draft_resume_version"),
        sa.CheckConstraint("job_posting_version >= 1", name="ck_message_draft_job_version"),
        sa.CheckConstraint(
            "style IN ('professional', 'concise', 'referral')",
            name="ck_message_draft_style",
        ),
        sa.CheckConstraint(
            "revision_type IN ('generated', 'edited')",
            name="ck_message_draft_revision_type",
        ),
        sa.CheckConstraint(
            "(version = 1 AND revision_type = 'generated' AND previous_version IS NULL) OR "
            "(version > 1 AND revision_type = 'edited' AND previous_version = version - 1)",
            name="ck_message_draft_revision_chain",
        ),
        sa.CheckConstraint(
            "(style = 'referral' AND referral_context IS NOT NULL) OR "
            "(style <> 'referral' AND referral_context IS NULL)",
            name="ck_message_draft_referral_context",
        ),
        sa.CheckConstraint("jsonb_typeof(skills) = 'array'", name="ck_message_draft_skills"),
        sa.CheckConstraint(
            "length(variant_content_fingerprint) = 64 AND "
            "length(generation_identity) = 64 AND "
            "length(content_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_message_draft_hashes",
        ),
        sa.CheckConstraint(
            "(company_snapshot_id IS NULL AND company_snapshot_version IS NULL AND "
            "company_snapshot_hash IS NULL AND company_freshness IS NULL) OR "
            "(company_snapshot_id IS NOT NULL AND company_snapshot_version >= 1 AND "
            "length(company_snapshot_hash) = 64 AND company_freshness IS NOT NULL)",
            name="ck_message_draft_company_identity",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_message_draft_variant_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id", "candidate_profile_version", "owner_id"],
            [
                "candidate_profile_versions.profile_id",
                "candidate_profile_versions.version",
                "candidate_profile_versions.owner_id",
            ],
            name="fk_message_draft_profile_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_message_draft_resume_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id", "job_posting_version", "owner_id"],
            ["job_postings.id", "job_postings.version", "job_postings.owner_id"],
            name="fk_message_draft_job_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_snapshot_id", "company_snapshot_version", "owner_id"],
            [
                "company_snapshots.snapshot_id",
                "company_snapshots.version",
                "company_snapshots.owner_id",
            ],
            name="fk_message_draft_company_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id", "previous_version", "owner_id"],
            ["message_drafts.id", "message_drafts.version", "message_drafts.owner_id"],
            name="fk_message_draft_previous_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_message_draft_identity"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_message_draft_owner_key"),
    )
    op.create_index("ix_message_drafts_id", "message_drafts", ["id"], unique=False)
    op.create_index("ix_message_drafts_owner_id", "message_drafts", ["owner_id"], unique=False)
    op.create_index(
        "ix_message_drafts_variant",
        "message_drafts",
        ["owner_id", "resume_variant_id", "draft_created_at"],
        unique=False,
    )
    op.create_index(
        "uq_message_draft_owner_generation",
        "message_drafts",
        ["owner_id", "generation_identity"],
        unique=True,
        postgresql_where=sa.text("version = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_message_draft_owner_generation", table_name="message_drafts")
    op.drop_index("ix_message_drafts_variant", table_name="message_drafts")
    op.drop_index("ix_message_drafts_owner_id", table_name="message_drafts")
    op.drop_index("ix_message_drafts_id", table_name="message_drafts")
    op.drop_table("message_drafts")
