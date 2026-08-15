"""Rendered production Compose least-privilege contracts."""

import importlib.util
from pathlib import Path

CHECK_PATH = Path(__file__).parents[3] / "deploy" / "check_compose_security.py"
SPEC = importlib.util.spec_from_file_location("nora_compose_security", CHECK_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
validate_secret_mounts = CHECK.validate_secret_mounts


def _model() -> dict[str, object]:
    services = {}
    for service, targets in CHECK.EXPECTED_SECRET_TARGETS.items():
        services[service] = {
            "volumes": [{"target": target, "read_only": True} for target in sorted(targets)]
            + [{"target": "/backup", "read_only": False}]
        }
    return {"services": services}


def test_privileged_operation_services_receive_only_expected_secrets() -> None:
    assert validate_secret_mounts(_model()) == []


def test_backup_services_reject_management_or_application_secret_leaks() -> None:
    model = _model()
    services = model["services"]
    assert isinstance(services, dict)
    backup_client = services["backup-storage-client"]
    assert isinstance(backup_client, dict)
    volumes = backup_client["volumes"]
    assert isinstance(volumes, list)
    volumes.append({"target": "/run/secrets/minio_root_password", "read_only": True})

    errors = validate_secret_mounts(model)

    assert any("backup-storage-client Secret targets differ" in error for error in errors)


def test_secret_mounts_must_be_read_only() -> None:
    model = _model()
    services = model["services"]
    assert isinstance(services, dict)
    metadata = services["backup-metadata"]
    assert isinstance(metadata, dict)
    volumes = metadata["volumes"]
    assert isinstance(volumes, list)
    volumes[0]["read_only"] = False

    assert any("writable Secret mounts" in error for error in validate_secret_mounts(model))
