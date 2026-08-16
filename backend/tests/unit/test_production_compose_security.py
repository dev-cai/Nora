"""Rendered production Compose least-privilege contracts."""

import importlib.util
from pathlib import Path

CHECK_PATH = Path(__file__).parents[3] / "deploy" / "check_compose_security.py"
SPEC = importlib.util.spec_from_file_location("nora_compose_security", CHECK_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
validate_secret_mounts = CHECK.validate_secret_mounts
validate_production_topology = CHECK.validate_production_topology


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


def _topology_model() -> dict[str, object]:
    return {
        "services": {
            "web": {
                "image": "ghcr.io/dev-cai/nora-web@sha256:" + "1" * 64,
                "ports": [{"host_ip": "127.0.0.1", "published": "18080", "target": 5173}],
                "networks": {"edge": {"ipv4_address": "172.28.0.10"}},
            },
            "api": {
                "image": "ghcr.io/dev-cai/nora-api@sha256:" + "2" * 64,
                "environment": {"TRUSTED_PROXY_CIDR": "172.28.0.10/32"},
                "networks": {"edge": None, "data": None},
            },
            "db": {"image": "postgres:16", "networks": {"data": None}},
            "storage": {"image": "minio/minio", "networks": {"data": None}},
        },
        "networks": {
            "edge": {
                "internal": False,
                "ipam": {"config": [{"subnet": "172.28.0.0/24"}]},
            },
            "data": {"internal": True},
        },
        "volumes": {},
    }


def test_production_topology_publishes_only_fixed_localhost_web() -> None:
    assert validate_production_topology(_topology_model()) == []


def test_production_topology_rejects_ingress_broad_proxy_trust_and_private_ports() -> None:
    model = _topology_model()
    services = model["services"]
    assert isinstance(services, dict)
    services["ingress"] = {"image": "caddy:2", "ports": [{"target": 443}]}
    api = services["api"]
    assert isinstance(api, dict)
    api["ports"] = [{"target": 8000}]
    api["environment"] = {"TRUSTED_PROXY_CIDR": "172.28.0.0/24"}
    web = services["web"]
    assert isinstance(web, dict)
    web["ports"] = [{"host_ip": "0.0.0.0", "published": "18080", "target": 5173}]
    networks = model["networks"]
    assert isinstance(networks, dict)
    edge = networks["edge"]
    assert isinstance(edge, dict)
    edge["ipam"] = {"config": [{"subnet": "172.28.1.0/24"}]}
    model["volumes"] = {"caddy_data": {}}

    errors = validate_production_topology(model)

    assert any("ingress service" in error for error in errors)
    assert any("Caddy image" in error for error in errors)
    assert any("only web" in error for error in errors)
    assert any("127.0.0.1" in error for error in errors)
    assert any("172.28.0.10/32" in error for error in errors)
    assert any("172.28.0.0/24" in error for error in errors)
    assert any("Caddy volumes" in error for error in errors)
