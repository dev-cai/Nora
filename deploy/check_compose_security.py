"""Validate rendered production Compose Secret mounts for privileged operations."""

from __future__ import annotations

import json
import sys
from typing import Any

EXPECTED_SECRET_TARGETS = {
    "backup-metadata": {"/run/secrets/database_url"},
    "backup-storage-client": {
        "/run/secrets/artifact_backup_access_key",
        "/run/secrets/artifact_backup_secret_key",
    },
    "reconcile": {
        "/run/secrets/artifact_access_key",
        "/run/secrets/artifact_secret_key",
        "/run/secrets/database_url",
    },
    "restore-storage-client": {
        "/run/secrets/minio_root_password",
        "/run/secrets/minio_root_user",
    },
}


def validate_secret_mounts(model: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    services = model.get("services")
    if not isinstance(services, dict):
        return ["rendered Compose model must contain services"]

    for service_name, expected_targets in EXPECTED_SECRET_TARGETS.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            errors.append(f"missing service {service_name}")
            continue
        volumes = service.get("volumes") or []
        secret_volumes = [
            volume
            for volume in volumes
            if isinstance(volume, dict)
            and str(volume.get("target", "")).startswith("/run/secrets/")
        ]
        actual_targets = {str(volume["target"]) for volume in secret_volumes}
        if actual_targets != expected_targets:
            errors.append(
                f"{service_name} Secret targets differ: "
                f"expected={sorted(expected_targets)} actual={sorted(actual_targets)}"
            )
        writable = [
            str(volume["target"]) for volume in secret_volumes if not volume.get("read_only")
        ]
        if writable:
            errors.append(f"{service_name} has writable Secret mounts: {sorted(writable)}")
    return errors


def main() -> None:
    try:
        model = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SystemExit(f"production_compose_security_error=invalid JSON: {exc}") from exc
    errors = validate_secret_mounts(model)
    if errors:
        for error in errors:
            print(f"production_compose_security_error={error}")
        raise SystemExit(2)
    print("production_compose_security=passed")


if __name__ == "__main__":
    main()
