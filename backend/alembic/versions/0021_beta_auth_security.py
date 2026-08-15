"""Add Beta owner, session version and persistent authentication buckets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_beta_auth_security"
down_revision: str | None = "0020_application_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("session_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_check_constraint("ck_users_session_version", "users", "session_version >= 1")
    op.create_table(
        "beta_owner",
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("slot = 1", name="ck_beta_owner_singleton_slot"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("slot"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "identity_management_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("request_identity", sa.String(length=255), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resulting_session_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "operation IN ('bootstrap', 'recover')", name="ck_identity_management_operation"
        ),
        sa.CheckConstraint(
            "length(identity_fingerprint) = 64",
            name="ck_identity_management_fingerprint",
        ),
        sa.CheckConstraint(
            "resulting_session_version >= 1",
            name="ck_identity_management_session_version",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation", "request_identity", name="uq_identity_management_request"),
    )
    op.create_table(
        "authentication_rate_limits",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dimension IN ('coarse_client', 'login_target', 'login_client')",
            name="ck_auth_rate_limit_dimension",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_auth_rate_limit_count"),
        sa.CheckConstraint("length(bucket_key) = 64", name="ck_auth_rate_limit_bucket_key"),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_authentication_rate_limits_expires_at",
        "authentication_rate_limits",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authentication_rate_limits_expires_at", table_name="authentication_rate_limits"
    )
    op.drop_table("authentication_rate_limits")
    op.drop_table("identity_management_requests")
    op.drop_table("beta_owner")
    op.drop_constraint("ck_users_session_version", "users", type_="check")
    op.drop_column("users", "session_version")
