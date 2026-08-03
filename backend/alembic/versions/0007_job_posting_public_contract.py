"""Require complete public metadata for job posting snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job_posting_public_contract"
down_revision: str | None = "0006_audit_event_target_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE job_postings
            SET
                job_title = CASE
                    WHEN job_title IS NULL OR length(trim(job_title)) = 0
                    THEN '未提供职位'
                    ELSE job_title
                END,
                company_name = CASE
                    WHEN company_name IS NULL OR length(trim(company_name)) = 0
                    THEN '未提供公司'
                    ELSE company_name
                END,
                location = CASE
                    WHEN location IS NULL OR length(trim(location)) = 0
                    THEN '未提供地点'
                    ELSE location
                END
            """
        )
    )
    for column_name in ("job_title", "company_name", "location"):
        op.alter_column(
            "job_postings",
            column_name,
            existing_type=sa.String(length=200),
            nullable=False,
        )
        op.create_check_constraint(
            f"ck_job_postings_{column_name}_nonempty",
            "job_postings",
            f"length(trim({column_name})) > 0",
        )


def downgrade() -> None:
    for column_name in reversed(("job_title", "company_name", "location")):
        op.drop_constraint(
            f"ck_job_postings_{column_name}_nonempty",
            "job_postings",
            type_="check",
        )
        op.alter_column(
            "job_postings",
            column_name,
            existing_type=sa.String(length=200),
            nullable=True,
        )
