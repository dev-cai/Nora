"""Add user-confirmed manual application records and transitions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_application_records"
down_revision: str | None = "0019_company_assessment_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STATUSES = "'planned', 'applied', 'interviewing', 'offer_received', 'rejected', 'withdrawn'"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_application_decision_record_input",
        "application_decisions",
        ["id", "decision_case_id", "owner_id"],
    )
    op.create_table(
        "application_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("application_decision_id", sa.Uuid(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("resume_variant_id", sa.Uuid(), nullable=False),
        sa.Column("resume_variant_version", sa.Integer(), nullable=False),
        sa.Column("variant_content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resume_pdf_id", sa.Uuid(), nullable=True),
        sa.Column("resume_pdf_version", sa.Integer(), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_version", sa.Integer(), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("message_draft_id", sa.Uuid(), nullable=True),
        sa.Column("message_draft_version", sa.Integer(), nullable=True),
        sa.Column("message_content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("application_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_application_record_version"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_application_record_status"),
        sa.CheckConstraint("created_by = owner_id", name="ck_application_record_creator_owner"),
        sa.CheckConstraint(
            "length(variant_content_fingerprint) = 64 AND length(request_fingerprint) = 64",
            name="ck_application_record_hashes",
        ),
        sa.CheckConstraint(
            "(resume_pdf_id IS NULL AND resume_pdf_version IS NULL AND artifact_id IS NULL AND "
            "artifact_version IS NULL AND artifact_sha256 IS NULL) OR "
            "(resume_pdf_id IS NOT NULL AND resume_pdf_version >= 1 AND artifact_id IS NOT NULL "
            "AND artifact_version >= 1 AND length(artifact_sha256) = 64)",
            name="ck_application_record_pdf_reference",
        ),
        sa.CheckConstraint(
            "(message_draft_id IS NULL AND message_draft_version IS NULL AND "
            "message_content_fingerprint IS NULL) OR (message_draft_id IS NOT NULL AND "
            "message_draft_version >= 1 AND length(message_content_fingerprint) = 64)",
            name="ck_application_record_draft_reference",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["application_decision_id", "decision_case_id", "owner_id"],
            [
                "application_decisions.id",
                "application_decisions.decision_case_id",
                "application_decisions.owner_id",
            ],
            name="fk_application_record_apply_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resume_variant_id", "resume_variant_version", "owner_id"],
            ["resume_variants.id", "resume_variants.version", "resume_variants.owner_id"],
            name="fk_application_record_variant_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resume_pdf_id", "resume_pdf_version", "owner_id"],
            ["resume_pdfs.id", "resume_pdfs.version", "resume_pdfs.owner_id"],
            name="fk_application_record_pdf_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_application_record_artifact_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_draft_id", "message_draft_version", "owner_id"],
            ["message_drafts.id", "message_drafts.version", "message_drafts.owner_id"],
            name="fk_application_record_draft_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_application_record_identity"),
        sa.UniqueConstraint(
            "owner_id",
            "application_decision_id",
            name="uq_application_record_owner_decision",
        ),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_application_record_owner_key"),
    )
    op.create_index(
        "ix_application_records_owner_id", "application_records", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_application_records_owner_updated",
        "application_records",
        ["owner_id", "application_updated_at"],
        unique=False,
    )

    op.create_table(
        "application_record_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("application_record_id", sa.Uuid(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint("record_version >= 2", name="ck_application_transition_version"),
        sa.CheckConstraint(
            f"from_status IN ({STATUSES}) AND to_status IN ({STATUSES}) "
            "AND from_status <> to_status",
            name="ck_application_transition_statuses",
        ),
        sa.CheckConstraint("source = 'user_confirmation'", name="ck_application_transition_source"),
        sa.CheckConstraint("actor_id = owner_id", name="ck_application_transition_actor_owner"),
        sa.CheckConstraint(
            "to_status <> 'applied' OR channel IS NOT NULL",
            name="ck_application_transition_applied_channel",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_application_transition_fingerprint",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["application_record_id", "owner_id"],
            ["application_records.id", "application_records.owner_id"],
            name="fk_application_transition_record_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_record_id",
            "record_version",
            name="uq_application_transition_record_version",
        ),
        sa.UniqueConstraint(
            "owner_id", "idempotency_key", name="uq_application_transition_owner_key"
        ),
    )
    op.create_index(
        "ix_application_record_transitions_owner_id",
        "application_record_transitions",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_transitions_record",
        "application_record_transitions",
        ["owner_id", "application_record_id", "record_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_transitions_record", table_name="application_record_transitions")
    op.drop_index(
        "ix_application_record_transitions_owner_id",
        table_name="application_record_transitions",
    )
    op.drop_table("application_record_transitions")
    op.drop_index("ix_application_records_owner_updated", table_name="application_records")
    op.drop_index("ix_application_records_owner_id", table_name="application_records")
    op.drop_table("application_records")
    op.drop_constraint(
        "uq_application_decision_record_input", "application_decisions", type_="unique"
    )
