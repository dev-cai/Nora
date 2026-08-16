"""Validate rendered production Compose topology and least-privilege mounts."""

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


def validate_production_topology(model: dict[str, Any]) -> list[str]:
    services = model.get("services")
    networks = model.get("networks")
    if not isinstance(services, dict):
        return ["rendered Compose model must contain services"]
    errors: list[str] = []
    if "ingress" in services:
        errors.append("production Compose must not contain an ingress service")
    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        image = str(service.get("image", "")).lower()
        if "caddy" in image:
            errors.append(f"production service {name} must not use a Caddy image")
        ports = service.get("ports") or []
        if name != "web" and ports:
            errors.append(f"only web may publish host ports; found {name}")
    web = services.get("web")
    if not isinstance(web, dict):
        errors.append("missing service web")
    else:
        ports = web.get("ports") or []
        if len(ports) != 1 or not isinstance(ports[0], dict):
            errors.append("web must publish exactly one structured port")
        else:
            port = ports[0]
            if port.get("host_ip") != "127.0.0.1":
                errors.append("web published port must bind 127.0.0.1")
            if port.get("target") != 5173:
                errors.append("web published target must be 5173")
        web_networks = web.get("networks") or {}
        edge = web_networks.get("edge") if isinstance(web_networks, dict) else None
        if not isinstance(edge, dict) or edge.get("ipv4_address") != "172.28.0.10":
            errors.append("web must use fixed edge address 172.28.0.10")
    api = services.get("api")
    if not isinstance(api, dict):
        errors.append("missing service api")
    else:
        environment = api.get("environment") or {}
        if not isinstance(environment, dict) or environment.get("TRUSTED_PROXY_CIDR") != (
            "172.28.0.10/32"
        ):
            errors.append("api TRUSTED_PROXY_CIDR must be 172.28.0.10/32")
    if not isinstance(networks, dict):
        errors.append("rendered Compose model must contain networks")
    else:
        edge_network = networks.get("edge")
        expected_edge_ipam = {"config": [{"subnet": "172.28.0.0/24"}]}
        if not isinstance(edge_network, dict) or edge_network.get("ipam") != expected_edge_ipam:
            errors.append("edge network subnet must be exactly 172.28.0.0/24")
        data = networks.get("data")
        if not isinstance(data, dict) or data.get("internal") is not True:
            errors.append("data network must be internal")
    volumes = model.get("volumes") or {}
    if isinstance(volumes, dict) and any("caddy" in str(name).lower() for name in volumes):
        errors.append("production Compose must not contain Caddy volumes")
    return errors


def main() -> None:
    try:
        model = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SystemExit(f"production_compose_security_error=invalid JSON: {exc}") from exc
    errors = [*validate_production_topology(model), *validate_secret_mounts(model)]
    if errors:
        for error in errors:
            print(f"production_compose_security_error={error}")
        raise SystemExit(2)
    print("production_compose_security=passed")


if __name__ == "__main__":
    main()
