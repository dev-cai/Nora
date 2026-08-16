"""Recovery archive extraction safety contracts."""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

EXTRACTOR_PATH = Path(__file__).parents[3] / "deploy" / "extract_recovery.py"
SPEC = importlib.util.spec_from_file_location("nora_recovery_extractor", EXTRACTOR_PATH)
assert SPEC is not None and SPEC.loader is not None
EXTRACTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACTOR)
extract_recovery_archive = EXTRACTOR.extract_recovery_archive


def test_recovery_extractor_accepts_expected_files_and_objects(tmp_path: Path) -> None:
    archive = tmp_path / "recovery.tar"
    with tarfile.open(archive, mode="w") as output:
        _add_file(output, "./postgres.dump", b"database")
        _add_file(output, "./artifact-manifest.jsonl", b"")
        _add_file(output, "./artifact-deletion-ledger.jsonl", b"")
        _add_file(output, "./backup-metadata.json", b"{}")
        _add_file(output, "./backup-record.json", b"{}")
        _add_file(output, "./objects/private/artifact", b"content")

    destination = tmp_path / "restored"
    extract_recovery_archive(archive, destination)

    assert (destination / "postgres.dump").read_bytes() == b"database"
    assert (destination / "objects/private/artifact").read_bytes() == b"content"


@pytest.mark.parametrize("name", ["../outside", "/absolute", "unknown-file"])
def test_recovery_extractor_rejects_unsafe_or_unknown_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "recovery.tar"
    with tarfile.open(archive, mode="w") as output:
        _add_file(output, name, b"unsafe")

    with pytest.raises(ValueError, match="unsafe path|unknown top-level"):
        extract_recovery_archive(archive, tmp_path / "restored")


def test_recovery_extractor_rejects_links(tmp_path: Path) -> None:
    archive = tmp_path / "recovery.tar"
    with tarfile.open(archive, mode="w") as output:
        link = tarfile.TarInfo("objects/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        output.addfile(link)

    with pytest.raises(ValueError, match="links and special entries"):
        extract_recovery_archive(archive, tmp_path / "restored")


def _add_file(output: tarfile.TarFile, name: str, payload: bytes) -> None:
    entry = tarfile.TarInfo(name)
    entry.size = len(payload)
    output.addfile(entry, io.BytesIO(payload))
