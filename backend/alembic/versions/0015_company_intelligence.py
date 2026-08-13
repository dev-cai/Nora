"""Add immutable CompanySnapshot and fixed CompanyAssessment storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_company_intelligence"
down_revision: str | None = "0014_artifacts_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_snapshots",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("size", sa.String(length=200), nullable=True),
        sa.Column("size_status", sa.String(length=16), nullable=False),
        sa.Column("industry", sa.String(length=200), nullable=True),
        sa.Column("industry_status", sa.String(length=16), nullable=False),
        sa.Column("review_summary", sa.String(length=2000), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_tier", sa.String(length=32), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("acquisition_method", sa.String(length=100), nullable=False),
        sa.Column("license_note", sa.String(length=500), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("freshness", sa.String(length=16), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_company_snapshot_version"),
        sa.CheckConstraint("source_version >= 1", name="ck_company_snapshot_source_version"),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_company_snapshot_sha256"),
        sa.CheckConstraint(
            "length(source_content_sha256) = 64", name="ck_company_snapshot_source_sha256"
        ),
        sa.CheckConstraint(
            "size_status IN ('confirmed', 'unconfirmed', 'unknown', 'conflicted', "
            "'superseded') AND industry_status IN ('confirmed', 'unconfirmed', 'unknown', "
            "'conflicted', 'superseded') AND review_status IN ('confirmed', 'unconfirmed', "
            "'unknown', 'conflicted', 'superseded')",
            name="ck_company_snapshot_field_statuses",
        ),
        sa.CheckConstraint(
            "(size IS NULL) = (size_status = 'unknown') AND "
            "(industry IS NULL) = (industry_status = 'unknown') AND "
            "(review_summary IS NULL) = (review_status = 'unknown')",
            name="ck_company_snapshot_value_statuses",
        ),
        sa.CheckConstraint(
            "source_tier IN ('official/company', 'reputable_media', 'verified_platform', "
            "'anonymous_platform')",
            name="ck_company_snapshot_source_tier",
        ),
        sa.CheckConstraint(
            "freshness IN ('fresh', 'aging', 'stale', 'unknown')",
            name="ck_company_snapshot_freshness",
        ),
        sa.CheckConstraint(
            "NOT (source_tier = 'anonymous_platform' AND ('confirmed' IN "
            "(size_status, industry_status, review_status)))",
            name="ck_company_snapshot_anonymous_facts",
        ),
        sa.CheckConstraint(
            "NOT (freshness = 'stale' AND ('confirmed' IN "
            "(size_status, industry_status, review_status)))",
            name="ck_company_snapshot_stale_facts",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_id", "source_version", "owner_id"],
            ["source_documents.id", "source_documents.version", "source_documents.owner_id"],
            name="fk_company_snapshot_source_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "snapshot_id", "version", "owner_id", name="uq_company_snapshot_identity"
        ),
    )
    op.create_index(
        "ix_company_snapshots_snapshot_id", "company_snapshots", ["snapshot_id"], unique=False
    )
    op.create_index(
        "ix_company_snapshots_owner_id", "company_snapshots", ["owner_id"], unique=False
    )
    op.create_table(
        "company_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("decision_case_version", sa.Integer(), nullable=False),
        sa.Column("company_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("company_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("status_reason", sa.String(length=200), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("generation_identity", sa.String(length=64), nullable=False),
        sa.Column("assessment_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_company_assessment_version"),
        sa.CheckConstraint("decision_case_version >= 1", name="ck_company_assessment_case_version"),
        sa.CheckConstraint(
            "company_snapshot_version >= 1", name="ck_company_assessment_snapshot_version"
        ),
        sa.CheckConstraint(
            "decision_case_version = 1", name="ck_company_assessment_case_compat_version"
        ),
        sa.CheckConstraint(
            "length(generation_identity) = 64", name="ck_company_assessment_generation_identity"
        ),
        sa.CheckConstraint(
            "status IN ('available', 'unknown', 'conflicted', 'stale')",
            name="ck_company_assessment_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_id", "report_version", "decision_case_id", "owner_id"],
            [
                "decision_reports.id",
                "decision_reports.version",
                "decision_reports.decision_case_id",
                "decision_reports.owner_id",
            ],
            name="fk_company_assessment_report_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_case_id", "owner_id"],
            ["decision_cases.id", "decision_cases.owner_id"],
            name="fk_company_assessment_case_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_snapshot_id", "company_snapshot_version", "owner_id"],
            [
                "company_snapshots.snapshot_id",
                "company_snapshots.version",
                "company_snapshots.owner_id",
            ],
            name="fk_company_assessment_snapshot_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "report_id", "report_version", name="uq_company_assessment_report"
        ),
        sa.UniqueConstraint(
            "owner_id", "generation_identity", name="uq_company_assessment_generation"
        ),
    )
    op.create_index(
        "ix_company_assessments_owner_id", "company_assessments", ["owner_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_company_assessments_owner_id", table_name="company_assessments")
    op.drop_table("company_assessments")
    op.drop_index("ix_company_snapshots_owner_id", table_name="company_snapshots")
    op.drop_index("ix_company_snapshots_snapshot_id", table_name="company_snapshots")
    op.drop_table("company_snapshots")
