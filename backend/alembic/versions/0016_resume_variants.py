"""Add declarative templates and immutable resume variants."""

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_resume_variants"
down_revision: str | None = "0015_company_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATES = (
    {
        "template_id": UUID("159f9891-54ac-4f19-9eb3-9c67db60c8d1"),
        "version": 1,
        "name": "清晰单栏",
        "definition": {
            "page_size": "a4",
            "density": "standard",
            "accent": "neutral",
            "section_order": ["basic_information", "experiences", "education", "skills"],
            "allowed_fields": [
                "basic_information.*",
                "experiences.*.*",
                "education.*.*",
                "skills.*.*",
            ],
            "required_fields": ["basic_information.display_name"],
        },
    },
    {
        "template_id": UUID("4af0bd86-a03a-43ce-b1ec-5bb04167b869"),
        "version": 1,
        "name": "紧凑技术",
        "definition": {
            "page_size": "a4",
            "density": "compact",
            "accent": "blue",
            "section_order": ["basic_information", "skills", "experiences", "education"],
            "allowed_fields": [
                "basic_information.*",
                "skills.*.*",
                "experiences.*.*",
                "education.*.*",
            ],
            "required_fields": ["basic_information.display_name"],
        },
    },
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_application_decision_variant_input",
        "application_decisions",
        ["id", "decision_case_id", "resume_version_id", "resume_version", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_decision_case_job_owner",
        "decision_cases",
        ["id", "job_posting_id", "job_posting_version", "owner_id"],
    )
    op.create_unique_constraint(
        "uq_decision_case_requirement_owner",
        "decision_cases",
        ["id", "job_requirement_snapshot_id", "job_requirement_snapshot_version", "owner_id"],
    )
    op.create_table(
        "template_definitions",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_template_definition_version"),
        sa.CheckConstraint("length(definition_hash) = 64", name="ck_template_definition_hash"),
        sa.CheckConstraint(
            "jsonb_typeof(definition) = 'object'", name="ck_template_definition_json"
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("template_id", "version", name="uq_template_definition_identity"),
    )
    op.create_index(
        "ix_template_definitions_template_id",
        "template_definitions",
        ["template_id"],
        unique=False,
    )
    table = sa.table(
        "template_definitions",
        sa.column("record_id", sa.Uuid()),
        sa.column("template_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("definition", postgresql.JSONB()),
        sa.column("definition_hash", sa.String()),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    published_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "record_id": UUID("da1d78dd-e298-4ff2-9e0d-5ca73cba32c1")
                if index == 0
                else UUID("9f0a40e1-8c18-4f52-83dd-e62d7ad914e4"),
                "template_id": item["template_id"],
                "version": item["version"],
                "name": item["name"],
                "definition": item["definition"],
                "definition_hash": _definition_hash(item),
                "published_at": published_at,
            }
            for index, item in enumerate(TEMPLATES)
        ],
    )
    op.create_table(
        "resume_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("application_decision_id", sa.Uuid(), nullable=False),
        sa.Column("decision_case_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_version", sa.Integer(), nullable=False),
        sa.Column("job_requirement_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("job_requirement_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("blocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("variant_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_resume_variant_version"),
        sa.CheckConstraint("job_posting_version >= 1", name="ck_resume_variant_job_version"),
        sa.CheckConstraint(
            "job_requirement_snapshot_version >= 1",
            name="ck_resume_variant_requirement_version",
        ),
        sa.CheckConstraint("resume_version >= 1", name="ck_resume_variant_resume_version"),
        sa.CheckConstraint("template_version >= 1", name="ck_resume_variant_template_version"),
        sa.CheckConstraint("jsonb_typeof(blocks) = 'array'", name="ck_resume_variant_blocks"),
        sa.CheckConstraint(
            "length(content_fingerprint) = 64", name="ck_resume_variant_fingerprint"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            [
                "application_decision_id",
                "decision_case_id",
                "resume_version_id",
                "resume_version",
                "owner_id",
            ],
            [
                "application_decisions.id",
                "application_decisions.decision_case_id",
                "application_decisions.resume_version_id",
                "application_decisions.resume_version",
                "application_decisions.owner_id",
            ],
            name="fk_resume_variant_apply_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_case_id", "job_posting_id", "job_posting_version", "owner_id"],
            [
                "decision_cases.id",
                "decision_cases.job_posting_id",
                "decision_cases.job_posting_version",
                "decision_cases.owner_id",
            ],
            name="fk_resume_variant_job_input",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "decision_case_id",
                "job_requirement_snapshot_id",
                "job_requirement_snapshot_version",
                "owner_id",
            ],
            [
                "decision_cases.id",
                "decision_cases.job_requirement_snapshot_id",
                "decision_cases.job_requirement_snapshot_version",
                "decision_cases.owner_id",
            ],
            name="fk_resume_variant_requirement_input",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id", "resume_version", "owner_id"],
            ["resume_versions.id", "resume_versions.version", "resume_versions.owner_id"],
            name="fk_resume_variant_resume_input",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["template_definitions.template_id", "template_definitions.version"],
            name="fk_resume_variant_template_input",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "version", "owner_id", name="uq_resume_variant_identity"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_resume_variant_owner_key"),
    )
    op.create_index("ix_resume_variants_owner_id", "resume_variants", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_resume_variants_owner_id", table_name="resume_variants")
    op.drop_table("resume_variants")
    op.drop_index("ix_template_definitions_template_id", table_name="template_definitions")
    op.drop_table("template_definitions")
    op.drop_constraint("uq_decision_case_requirement_owner", "decision_cases", type_="unique")
    op.drop_constraint("uq_decision_case_job_owner", "decision_cases", type_="unique")
    op.drop_constraint(
        "uq_application_decision_variant_input", "application_decisions", type_="unique"
    )


def _definition_hash(item: dict[str, object]) -> str:
    definition = item["definition"]
    assert isinstance(definition, dict)
    content = {**definition, "name": item["name"], "version": item["version"]}
    payload = json.dumps(content, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
