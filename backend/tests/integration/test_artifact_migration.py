"""Artifact/Source migration constraints."""

from pathlib import Path


def test_artifact_migration_declares_lifecycle_and_owner_constraints() -> None:
    migration = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0014_artifacts_sources.py"
    ).read_text(encoding="utf-8")
    for marker in (
        "uq_artifact_owner_key",
        "uq_artifact_id_version_owner",
        "fk_source_artifact_owner",
        "ck_artifact_tombstone",
        "ck_artifact_status",
        "ck_artifact_generation_identity",
    ):
        assert marker in migration
