"""Production Artifact reconciliation contracts."""

from app.apps.operations import ArtifactSnapshot, ObjectSnapshot, reconcile_artifacts


def _artifact(
    artifact_id: str,
    *,
    status: str = "available",
    object_key: str | None = None,
    size_bytes: int = 7,
    sha256: str = "a" * 64,
) -> ArtifactSnapshot:
    return ArtifactSnapshot(
        artifact_id=artifact_id,
        owner_id="owner-1",
        version=1,
        status=status,
        size_bytes=size_bytes,
        sha256=sha256,
        object_key=object_key,
        deleted_at="2026-08-15T00:00:00+00:00" if status == "deleted" else None,
    )


def test_reconciliation_passes_for_matching_available_and_deletion_pending_objects() -> None:
    artifacts = [
        _artifact("available", object_key="private/available"),
        _artifact("deleting", status="delete_pending", object_key="private/deleting"),
        _artifact("deleted", status="deleted"),
    ]
    objects = [
        ObjectSnapshot("private/available", 7, "a" * 64),
        ObjectSnapshot("private/deleting", 7, "a" * 64),
    ]

    report = reconcile_artifacts(artifacts, objects)

    assert report["status"] == "passed"
    assert report["counts"] == {
        "artifacts": 3,
        "objects": 2,
        "missing": 0,
        "corrupt": 0,
        "orphan": 0,
        "invalid_state": 0,
    }


def test_reconciliation_blocks_missing_corrupt_orphan_and_invalid_states() -> None:
    artifacts = [
        _artifact("missing", object_key="private/missing"),
        _artifact("corrupt", object_key="private/corrupt"),
        _artifact("invalid", object_key=None),
        _artifact("deleted", status="deleted", object_key="private/deleted"),
        _artifact("deleting-missing", status="delete_pending", object_key="private/deleting"),
        _artifact("failed-invalid", status="failed", object_key="private/failed"),
    ]
    objects = [
        ObjectSnapshot("private/corrupt", 8, "b" * 64),
        ObjectSnapshot("private/deleted", 7, "a" * 64),
        ObjectSnapshot("private/orphan-sensitive-key", 7, "a" * 64),
    ]

    report = reconcile_artifacts(artifacts, objects)

    assert report["status"] == "failed"
    assert report["counts"] == {
        "artifacts": 6,
        "objects": 3,
        "missing": 2,
        "corrupt": 1,
        "orphan": 1,
        "invalid_state": 3,
    }
    assert "private/" not in str(report)
