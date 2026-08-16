"""Offline production backup metadata export and Artifact reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from minio import Minio
from sqlalchemy import text

from app.infrastructure.config import get_settings
from app.infrastructure.database import create_database_engine


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    artifact_id: str
    owner_id: str
    version: int
    status: str
    size_bytes: int
    sha256: str
    object_key: str | None
    deleted_at: str | None


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    object_key: str
    size_bytes: int
    sha256: str


def reconcile_artifacts(
    artifacts: Sequence[ArtifactSnapshot], objects: Sequence[ObjectSnapshot]
) -> dict[str, Any]:
    """Return a deterministic report without exposing raw object keys."""

    object_required_statuses = {"available", "delete_pending", "delete_failed"}
    object_by_key = {item.object_key: item for item in objects}
    referenced_keys = {item.object_key for item in artifacts if item.object_key is not None}
    missing: list[dict[str, str]] = []
    corrupt: list[dict[str, str]] = []
    invalid_state: list[dict[str, str]] = []

    for artifact in sorted(artifacts, key=lambda item: (item.owner_id, item.artifact_id)):
        identity = {"artifact_id": artifact.artifact_id, "owner_id": artifact.owner_id}
        if artifact.status in object_required_statuses and artifact.object_key is None:
            invalid_state.append(identity | {"reason": f"{artifact.status}_without_object"})
            continue
        if artifact.status not in object_required_statuses and artifact.object_key is not None:
            invalid_state.append(identity | {"reason": f"{artifact.status}_with_object_reference"})
            continue
        if artifact.status not in object_required_statuses or artifact.object_key is None:
            continue
        stored = object_by_key.get(artifact.object_key)
        if stored is None:
            missing.append(identity | {"object_ref": _object_ref(artifact.object_key)})
        elif stored.size_bytes != artifact.size_bytes or stored.sha256 != artifact.sha256:
            corrupt.append(identity | {"object_ref": _object_ref(artifact.object_key)})

    orphan = [
        {"object_ref": _object_ref(item.object_key)}
        for item in sorted(objects, key=lambda item: item.object_key)
        if item.object_key not in referenced_keys
    ]
    counts = {
        "artifacts": len(artifacts),
        "objects": len(objects),
        "missing": len(missing),
        "corrupt": len(corrupt),
        "orphan": len(orphan),
        "invalid_state": len(invalid_state),
    }
    return {
        "status": "passed" if not (missing or corrupt or orphan or invalid_state) else "failed",
        "counts": counts,
        "missing": missing,
        "corrupt": corrupt,
        "orphan": orphan,
        "invalid_state": invalid_state,
    }


async def export_metadata(output_dir: Path) -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("database configuration is required")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifacts = await _load_artifacts()
    schema_revision = await _load_schema_revision()
    available = [item for item in artifacts if item.status == "available"]
    deletion = [
        item for item in artifacts if item.status in {"delete_pending", "delete_failed", "deleted"}
    ]
    _write_json_lines(output_dir / "artifact-manifest.jsonl", available)
    _write_json_lines(output_dir / "artifact-deletion-ledger.jsonl", deletion)
    _write_json(
        output_dir / "backup-metadata.json",
        {
            "schema_revision": schema_revision,
            "artifact_count": len(artifacts),
            "available_artifact_count": len(available),
            "deletion_ledger_count": len(deletion),
        },
    )
    print(
        "backup_metadata=exported "
        f"artifacts={len(artifacts)} available={len(available)} deletions={len(deletion)}"
    )


async def reconcile(report_path: Path) -> bool:
    settings = get_settings()
    artifacts = await _load_artifacts()
    client = Minio(
        settings.artifact_storage_endpoint,
        access_key=settings.artifact_storage_access_key,
        secret_key=settings.artifact_storage_secret_key,
        secure=settings.artifact_storage_secure,
    )
    objects = await asyncio.to_thread(_load_objects, client, settings.artifact_storage_bucket)
    report = reconcile_artifacts(artifacts, objects)
    _write_json(report_path, report)
    counts = report["counts"]
    print(
        f"artifact_reconciliation={report['status']} artifacts={counts['artifacts']} "
        f"objects={counts['objects']} discrepancies="
        f"{counts['missing'] + counts['corrupt'] + counts['orphan'] + counts['invalid_state']}"
    )
    return report["status"] == "passed"


async def _load_artifacts() -> list[ArtifactSnapshot]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("database configuration is required")
    engine = create_database_engine(settings)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id, owner_id, version, status, size_bytes, sha256, object_key, "
                        "deleted_at FROM artifacts ORDER BY owner_id, id"
                    )
                )
            ).mappings()
            return [
                ArtifactSnapshot(
                    artifact_id=str(row["id"]),
                    owner_id=str(row["owner_id"]),
                    version=row["version"],
                    status=row["status"],
                    size_bytes=row["size_bytes"],
                    sha256=row["sha256"],
                    object_key=row["object_key"],
                    deleted_at=row["deleted_at"].isoformat() if row["deleted_at"] else None,
                )
                for row in rows
            ]
    finally:
        await engine.dispose()


async def _load_schema_revision() -> str:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("database configuration is required")
    engine = create_database_engine(settings)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if not isinstance(revision, str) or not revision:
                raise RuntimeError("database schema revision is unavailable")
            return revision
    finally:
        await engine.dispose()


def _load_objects(client: Minio, bucket: str) -> list[ObjectSnapshot]:
    objects: list[ObjectSnapshot] = []
    for item in client.list_objects(bucket, recursive=True):
        response = client.get_object(bucket, item.object_name)
        digest = hashlib.sha256()
        size = 0
        try:
            for chunk in response.stream(amt=1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        finally:
            response.close()
            response.release_conn()
        objects.append(
            ObjectSnapshot(object_key=item.object_name, size_bytes=size, sha256=digest.hexdigest())
        )
    return objects


def _write_json_lines(path: Path, values: Sequence[ArtifactSnapshot]) -> None:
    payload = "".join(
        json.dumps(asdict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        for value in values
    )
    _write_private(path, payload)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _write_private(path, json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def _write_private(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(payload)


def _object_ref(object_key: str) -> str:
    return hashlib.sha256(object_key.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nora production data operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export-metadata")
    export_parser.add_argument("--output-dir", type=Path, required=True)
    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()

    if arguments.command == "export-metadata":
        asyncio.run(export_metadata(arguments.output_dir))
        return
    if not asyncio.run(reconcile(arguments.report)):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
