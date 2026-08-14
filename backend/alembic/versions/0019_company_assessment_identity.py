"""Remove the fixed CompanyAssessment decision case version."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0019_company_assessment_identity"
down_revision: str | None = "0018_message_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _generation_identity(row: dict[str, Any], *, include_case_version: bool) -> str:
    values: dict[str, object] = {
        "company_snapshot_id": str(row["company_snapshot_id"]),
        "company_snapshot_version": row["company_snapshot_version"],
        "decision_case_id": str(row["decision_case_id"]),
        "generator_version": " ".join(str(row["generator_version"]).split()),
        "report_id": str(row["report_id"]),
        "report_version": row["report_version"],
    }
    if include_case_version:
        values["decision_case_version"] = row["decision_case_version"]
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _rewrite_generation_identities(*, include_case_version: bool) -> None:
    columns = [
        sa.column("id", sa.Uuid()),
        sa.column("owner_id", sa.Uuid()),
        sa.column("report_id", sa.Uuid()),
        sa.column("report_version", sa.Integer()),
        sa.column("decision_case_id", sa.Uuid()),
        sa.column("company_snapshot_id", sa.Uuid()),
        sa.column("company_snapshot_version", sa.Integer()),
        sa.column("generator_version", sa.String()),
        sa.column("generation_identity", sa.String()),
    ]
    if include_case_version:
        columns.append(sa.column("decision_case_version", sa.Integer()))
    assessments = sa.table("company_assessments", *columns)
    connection = op.get_bind()
    rows = [dict(row) for row in connection.execute(sa.select(assessments)).mappings()]
    identities = [
        (row["owner_id"], _generation_identity(row, include_case_version=include_case_version))
        for row in rows
    ]
    if len(identities) != len(set(identities)):
        raise RuntimeError("CompanyAssessment generation identities would not remain unique")

    for row, (_, identity) in zip(rows, identities, strict=True):
        result = connection.execute(
            sa.update(assessments)
            .where(assessments.c.id == row["id"])
            .values(generation_identity=identity)
        )
        if result.rowcount != 1:
            raise RuntimeError("CompanyAssessment generation identity rewrite was incomplete")


def upgrade() -> None:
    _rewrite_generation_identities(include_case_version=False)
    op.drop_constraint(
        "ck_company_assessment_case_compat_version",
        "company_assessments",
        type_="check",
    )
    op.drop_constraint(
        "ck_company_assessment_case_version",
        "company_assessments",
        type_="check",
    )
    op.drop_column("company_assessments", "decision_case_version")


def downgrade() -> None:
    op.add_column(
        "company_assessments",
        sa.Column(
            "decision_case_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    _rewrite_generation_identities(include_case_version=True)
    op.create_check_constraint(
        "ck_company_assessment_case_version",
        "company_assessments",
        "decision_case_version >= 1",
    )
    op.create_check_constraint(
        "ck_company_assessment_case_compat_version",
        "company_assessments",
        "decision_case_version = 1",
    )
    op.alter_column("company_assessments", "decision_case_version", server_default=None)
