"""Extract one Nora recovery archive without trusting tar paths or entry types."""

from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath

ALLOWED_FILES = {
    "artifact-deletion-ledger.jsonl",
    "artifact-manifest.jsonl",
    "backup-metadata.json",
    "backup-record.json",
    "postgres.dump",
}


def extract_recovery_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    with tarfile.open(archive, mode="r:") as source:
        for member in source:
            relative = _validated_path(member)
            if relative is None:
                continue
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("recovery archive file payload is unavailable")
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(stream, output, length=1024 * 1024)
                if output.tell() != member.size:
                    raise ValueError("recovery archive file size is inconsistent")


def _validated_path(member: tarfile.TarInfo) -> PurePosixPath | None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("recovery archive contains an unsafe path")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts:
        if member.isdir():
            return None
        raise ValueError("recovery archive root entry must be a directory")
    if parts[0] not in ALLOWED_FILES | {"objects"}:
        raise ValueError("recovery archive contains an unknown top-level entry")
    if parts[0] in ALLOWED_FILES and len(parts) != 1:
        raise ValueError("recovery archive metadata path is invalid")
    if not member.isfile() and not member.isdir():
        raise ValueError("recovery archive links and special entries are forbidden")
    if parts[0] in ALLOWED_FILES and not member.isfile():
        raise ValueError("recovery archive metadata entry must be a file")
    return PurePosixPath(*parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        extract_recovery_archive(arguments.archive, arguments.destination)
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise SystemExit(f"recovery_archive_error={exc}") from exc


if __name__ == "__main__":
    main()
