"""Add a structured target version to audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_audit_event_target_version"
down_revision: str | None = "0005_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("target_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_audit_events_target_version",
        "audit_events",
        "target_version >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_audit_events_target_version",
        "audit_events",
        type_="check",
    )
    op.drop_column("audit_events", "target_version")
