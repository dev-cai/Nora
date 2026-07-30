"""Add durable idempotency records for job posting creation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_job_posting_idempotency"
down_revision: str | None = "0003_job_postings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_posting_idempotency",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("job_posting_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_job_posting_idempotency_owner_key",
        ),
        sa.UniqueConstraint(
            "job_posting_id",
            name="uq_job_posting_idempotency_posting",
        ),
    )
    op.create_index(
        "ix_job_posting_idempotency_owner_id",
        "job_posting_idempotency",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_posting_idempotency_owner_id",
        table_name="job_posting_idempotency",
    )
    op.drop_table("job_posting_idempotency")
