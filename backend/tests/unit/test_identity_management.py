"""Identity operator command boundary tests."""

import json
from pathlib import Path

import pytest
from app.apps import identity_management


def test_management_command_hides_unexpected_configuration_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fail_settings() -> object:
        raise RuntimeError("database-password-and-connection-details")

    monkeypatch.setattr(identity_management, "Settings", fail_settings)

    exit_code = identity_management.main(
        [
            "recover-owner",
            "--request-id",
            "recover-safe-failure",
            "--password-file",
            str(tmp_path / "unused-password"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {
        "status": "failed",
        "request_id": "recover-safe-failure",
    }
    assert captured.err == ""
    assert "database-password" not in captured.out


def test_management_secret_accepts_consumer_group_read_and_rejects_symlinks(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "owner-password"
    secret.write_text("private-value\n", encoding="utf-8")
    secret.chmod(0o440)

    assert identity_management._read_secret(secret) == "private-value"

    link = tmp_path / "owner-password-link"
    link.symlink_to(secret)
    with pytest.raises(ValueError, match="non-symlink"):
        identity_management._read_secret(link)
