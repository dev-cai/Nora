"""Immutable Beta release manifest, workflow and host state-machine contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
DEPLOY_DIR = ROOT / "deploy"
sys.path.insert(0, str(DEPLOY_DIR))


def _module(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MANIFEST_MODULE = _module("nora_release_manifest", DEPLOY_DIR / "release_manifest.py")
RELEASE_MODULE = _module("nora_release", DEPLOY_DIR / "release.py")
CI_MODULE = _module("nora_release_ci", DEPLOY_DIR / "verify_release_ci.py")
CONTROL_MODULE = _module("nora_release_control", DEPLOY_DIR / "verify_release_control.py")
API_SMOKE_MODULE = _module("nora_beta_api_smoke", ROOT / "backend/scripts/beta_api_smoke.py")
ReleaseManifest = MANIFEST_MODULE.ReleaseManifest
ReleaseManager = RELEASE_MODULE.ReleaseManager
ReleaseFailure = RELEASE_MODULE.ReleaseFailure
REQUIRED_CI_CHECKS = MANIFEST_MODULE.REQUIRED_CI_CHECKS


def _manifest(*, compatible: bool = False, run_id: int = 42) -> object:
    commit = "a" * 40
    return ReleaseManifest(
        format_version=1,
        release_id=f"{commit[:12]}-{run_id}",
        repository="dev-cai/Nora",
        source_ref="refs/heads/main",
        commit_sha=commit,
        workflow_run_id=run_id,
        ci_check_run_ids={name: index + 1 for index, name in enumerate(REQUIRED_CI_CHECKS)},
        api_image=f"ghcr.io/dev-cai/nora-api@sha256:{'1' * 64}",
        web_image=f"ghcr.io/dev-cai/nora-web@sha256:{'2' * 64}",
        api_sbom_sha256="3" * 64,
        web_sbom_sha256="4" * 64,
        api_attestation_url="https://github.com/dev-cai/Nora/attestations/10",
        web_attestation_url="https://github.com/dev-cai/Nora/attestations/11",
        migration_revision="0022_interview_cases",
        schema_policy_sha256="7" * 64,
        previous_schema_compatible=compatible,
        created_at="2026-08-16T03:30:00Z",
    )


def _write_manifest(path: Path, manifest: object) -> None:
    path.write_text(
        json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _environment(path: Path) -> None:
    path.write_text(
        "NORA_COMPOSE_PROJECT=nora-beta\n"
        "NORA_PUBLIC_ORIGIN=https://nora.internal.test\n"
        "NORA_WEB_PORT=18080\n"
        f"NORA_API_IMAGE=ghcr.io/dev-cai/nora-api@sha256:{'5' * 64}\n"
        f"NORA_WEB_IMAGE=ghcr.io/dev-cai/nora-web@sha256:{'6' * 64}\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def test_release_manifest_is_exact_and_binds_every_required_check(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest.validate()
    path = tmp_path / "release.json"
    _write_manifest(path, manifest)
    restored = MANIFEST_MODULE.load_manifest(path)
    assert restored.release_id == manifest.release_id

    invalid = asdict(manifest)
    invalid["ci_check_run_ids"].pop("Browser E2E (decision flow)")
    with pytest.raises(ValueError, match="every required"):
        ReleaseManifest.from_dict(invalid)


def test_release_ci_requires_all_successful_named_main_checks() -> None:
    runs = [
        {"id": index + 100, "name": name, "status": "completed", "conclusion": "success"}
        for index, name in enumerate(REQUIRED_CI_CHECKS)
    ]
    assert set(CI_MODULE.successful_check_run_ids(runs)) == REQUIRED_CI_CHECKS

    runs[0]["conclusion"] = "failure"
    with pytest.raises(ValueError, match="not successful"):
        CI_MODULE.successful_check_run_ids(runs)

    rerun = {**runs[0], "id": 999, "conclusion": "success"}
    assert CI_MODULE.successful_check_run_ids([*runs, rerun])[str(rerun["name"])] == 999


def test_release_control_requires_reviewed_beta_environment_and_online_runner() -> None:
    environment = {
        "name": "beta",
        "can_admins_bypass": False,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
        "protection_rules": [
            {
                "type": "required_reviewers",
                "reviewers": [{"type": "User", "reviewer": {"login": "operator"}}],
            }
        ],
    }
    runners = [
        {
            "status": "online",
            "labels": [{"name": name} for name in CONTROL_MODULE.REQUIRED_RUNNER_LABELS],
        }
    ]
    assert CONTROL_MODULE.validate_environment(environment) == []
    assert CONTROL_MODULE.validate_runners(runners) == []

    environment["can_admins_bypass"] = True
    runners[0]["status"] = "offline"
    assert any("bypass" in error for error in CONTROL_MODULE.validate_environment(environment))
    assert any("online" in error for error in CONTROL_MODULE.validate_runners(runners))


def test_release_control_prefers_dedicated_administration_token_over_github_token() -> None:
    assert (
        CONTROL_MODULE.resolve_token(
            {"RELEASE_CONTROL_TOKEN": "dedicated", "GITHUB_TOKEN": "default"}
        )
        == "dedicated"
    )
    assert CONTROL_MODULE.resolve_token({"GITHUB_TOKEN": "default"}) == "default"
    assert CONTROL_MODULE.resolve_token({}) is None


def test_beta_workflow_verify_job_uses_dedicated_release_control_token() -> None:
    workflow = (ROOT / ".github/workflows/beta-deploy.yml").read_text(encoding="utf-8")
    assert "secrets.RELEASE_CONTROL_TOKEN" in workflow
    verify_section = workflow.split("verify:", 1)[1].split("\n  build:", 1)[0]
    assert "Verify protected Environment and dedicated Runner" in verify_section
    assert (
        "github.token"
        not in verify_section.split("Verify protected Environment and dedicated Runner", 1)[
            1
        ].split("- name:", 1)[0]
    )


def test_release_bundle_rejects_modified_sbom(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest_path = tmp_path / "release-manifest.json"
    _write_manifest(manifest_path, manifest)
    (tmp_path / "sbom-api.spdx.json").write_text("api", encoding="utf-8")
    (tmp_path / "sbom-web.spdx.json").write_text("web", encoding="utf-8")
    (tmp_path / "schema-compatibility.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ReleaseFailure, match="digest"):
        RELEASE_MODULE.verify_release_bundle(manifest_path, manifest)


def test_release_bundle_accepts_matching_sbom_and_reviewed_schema_policy(
    tmp_path: Path,
) -> None:
    policy = (DEPLOY_DIR / "schema-compatibility.json").read_bytes()
    api_sbom = b'{"name":"api"}'
    web_sbom = b'{"name":"web"}'
    manifest = replace(
        _manifest(),
        api_sbom_sha256=hashlib.sha256(api_sbom).hexdigest(),
        web_sbom_sha256=hashlib.sha256(web_sbom).hexdigest(),
        schema_policy_sha256=hashlib.sha256(policy).hexdigest(),
        previous_schema_compatible=False,
    )
    manifest_path = tmp_path / "release-manifest.json"
    _write_manifest(manifest_path, manifest)
    (tmp_path / "sbom-api.spdx.json").write_bytes(api_sbom)
    (tmp_path / "sbom-web.spdx.json").write_bytes(web_sbom)
    (tmp_path / "schema-compatibility.json").write_bytes(policy)

    RELEASE_MODULE.verify_release_bundle(manifest_path, manifest)


def test_beta_api_smoke_checks_readiness_and_negative_authentication_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = {
        ("/live", "GET"): 200,
        ("/ready", "GET"): 200,
        ("/auth/me", "GET"): 401,
        ("/auth/register", "POST"): 404,
        ("/auth/login", "POST"): 401,
    }

    def request(path: str, *, method: str = "GET", payload: object = None) -> int:
        del payload
        return statuses[(path, method)]

    monkeypatch.setattr(API_SMOKE_MODULE, "_request", request)
    API_SMOKE_MODULE.main()


def test_successful_deploy_records_eight_phases_and_promotes_atomically(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "production.env"
    state_dir = tmp_path / "releases"
    manifest_path = tmp_path / "manifest.json"
    _environment(env_file)
    manifest = _manifest()
    _write_manifest(manifest_path, manifest)
    commands: list[list[str]] = []

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )
    manager.deploy(manifest_path)

    events = [
        json.loads(line)
        for line in (state_dir / manifest.release_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    terminal = [
        (event["phase"], event["status"])
        for event in events
        if event["status"] in {"passed", "skipped"}
    ]
    assert terminal == [
        ("preflight", "passed"),
        ("backup", "skipped"),
        ("pull", "passed"),
        ("migrate", "passed"),
        ("start", "passed"),
        ("internal-smoke", "passed"),
        ("public-smoke", "passed"),
        ("promote", "passed"),
    ]
    assert json.loads((state_dir / "last-healthy.json").read_text())["release_id"] == (
        manifest.release_id
    )
    assert manifest.api_image in env_file.read_text(encoding="utf-8")
    assert any("beta_api_smoke.py" in argument for command in commands for argument in command)
    assert any(
        "artifact_storage_smoke.py" in argument for command in commands for argument in command
    )
    assert any("public_smoke.py" in argument for command in commands for argument in command)


def test_failed_pull_does_not_replace_last_healthy_release(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    state_dir = tmp_path / "releases"
    state_dir.mkdir(mode=0o700)
    manifest_path = tmp_path / "manifest.json"
    _environment(env_file)
    manifest = _manifest(run_id=43)
    _write_manifest(manifest_path, manifest)
    previous = {
        "release_id": "b" * 12 + "-7",
        "migration_revision": manifest.migration_revision,
        "environment_file": str(tmp_path / "previous.env"),
    }
    (state_dir / "last-healthy.json").write_text(json.dumps(previous), encoding="utf-8")

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        if "pull" in arguments:
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )
    with pytest.raises(subprocess.CalledProcessError):
        manager.deploy(manifest_path)

    assert json.loads((state_dir / "last-healthy.json").read_text()) == previous
    assert "sha256:" + "5" * 64 in env_file.read_text(encoding="utf-8")


def test_internal_smoke_failure_only_rolls_back_when_schema_is_declared_compatible(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "production.env"
    state_dir = tmp_path / "releases"
    state_dir.mkdir(mode=0o700)
    manifest_path = tmp_path / "manifest.json"
    previous_env = tmp_path / "previous.env"
    _environment(env_file)
    _environment(previous_env)
    manifest = _manifest(compatible=True, run_id=44)
    _write_manifest(manifest_path, manifest)
    previous = {
        "release_id": "b" * 12 + "-8",
        "commit_sha": "b" * 40,
        "workflow_run_id": 8,
        "api_image": f"ghcr.io/dev-cai/nora-api@sha256:{'5' * 64}",
        "web_image": f"ghcr.io/dev-cai/nora-web@sha256:{'6' * 64}",
        "migration_revision": "0021_beta_auth_security",
        "environment_file": str(previous_env),
        "operation": "deploy",
        "recorded_at": "2026-08-15T00:00:00Z",
    }
    (state_dir / "last-healthy.json").write_text(json.dumps(previous), encoding="utf-8")
    failed_once = False

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal failed_once
        if (
            any(value.endswith("artifact_storage_smoke.py") for value in arguments)
            and not failed_once
        ):
            failed_once = True
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )
    with pytest.raises(subprocess.CalledProcessError):
        manager.deploy(manifest_path)

    current = json.loads((state_dir / "current.json").read_text())
    assert current["release_id"] == previous["release_id"]
    assert current["operation"] == "rollback"
    assert json.loads((state_dir / "last-healthy.json").read_text()) == current


def test_public_smoke_failure_without_previous_release_stops_candidate_before_promotion(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "production.env"
    state_dir = tmp_path / "releases"
    manifest_path = tmp_path / "manifest.json"
    _environment(env_file)
    original_environment = env_file.read_text(encoding="utf-8")
    manifest = _manifest(run_id=45)
    _write_manifest(manifest_path, manifest)
    commands: list[list[str]] = []

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        if any(value.endswith("public_smoke.py") for value in arguments):
            assert env_file.read_text(encoding="utf-8") == original_environment
            assert not (state_dir / "current.json").exists()
            assert not (state_dir / "last-healthy.json").exists()
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )

    with pytest.raises(subprocess.CalledProcessError):
        manager.deploy(manifest_path)

    assert env_file.read_text(encoding="utf-8") == original_environment
    assert not (state_dir / "current.json").exists()
    assert not (state_dir / "last-healthy.json").exists()
    assert commands[-1][-3:] == ["stop", "web", "api"]
    result = json.loads((state_dir / manifest.release_id / "result.json").read_text())
    assert result == {
        "error": "CalledProcessError",
        "phase": "public-smoke",
        "status": "failed",
    }


def test_failed_public_smoke_during_automatic_rollback_never_records_rollback_healthy(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "production.env"
    previous_env = tmp_path / "previous.env"
    state_dir = tmp_path / "releases"
    state_dir.mkdir(mode=0o700)
    manifest_path = tmp_path / "manifest.json"
    _environment(env_file)
    _environment(previous_env)
    manifest = _manifest(run_id=46)
    _write_manifest(manifest_path, manifest)
    previous = {
        "release_id": "b" * 12 + "-10",
        "commit_sha": "b" * 40,
        "workflow_run_id": 10,
        "api_image": f"ghcr.io/dev-cai/nora-api@sha256:{'5' * 64}",
        "web_image": f"ghcr.io/dev-cai/nora-web@sha256:{'6' * 64}",
        "migration_revision": manifest.migration_revision,
        "environment_file": str(previous_env),
        "operation": "deploy",
        "recorded_at": "2026-08-15T00:00:00Z",
    }
    (state_dir / "last-healthy.json").write_text(json.dumps(previous), encoding="utf-8")

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        if any(value.endswith("public_smoke.py") for value in arguments):
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )

    with pytest.raises(ReleaseFailure, match="automatic rollback failed"):
        manager.deploy(manifest_path)

    assert json.loads((state_dir / "last-healthy.json").read_text()) == previous
    assert not (state_dir / "current.json").exists()
    assert list(state_dir.glob("rollback-*")) == []


def test_manual_rollback_refuses_cross_schema_target(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    state_dir = tmp_path / "releases"
    target_id = "b" * 12 + "-9"
    target_dir = state_dir / target_id
    target_dir.mkdir(parents=True)
    os.chmod(state_dir, 0o700)
    _environment(env_file)
    (target_dir / "result.json").write_text(
        json.dumps({"status": "healthy", "migration_revision": "0021_beta_auth_security"}),
        encoding="utf-8",
    )
    (state_dir / "current.json").write_text(
        json.dumps({"migration_revision": "0022_interview_cases"}), encoding="utf-8"
    )
    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=lambda arguments: subprocess.CompletedProcess(arguments, 0, "", ""),
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )
    with pytest.raises(ReleaseFailure, match="isolated restore"):
        manager.rollback(target_id, "operator request")


def test_manual_rollback_requires_public_smoke_before_updating_pointers(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    target_env = tmp_path / "target.env"
    state_dir = tmp_path / "releases"
    target_id = "b" * 12 + "-11"
    target_dir = state_dir / target_id
    target_dir.mkdir(parents=True)
    os.chmod(state_dir, 0o700)
    _environment(env_file)
    _environment(target_env)
    current = {"release_id": "c" * 12 + "-12", "migration_revision": "0022_interview_cases"}
    target = {
        "status": "healthy",
        "release_id": target_id,
        "commit_sha": "b" * 40,
        "workflow_run_id": 11,
        "api_image": f"ghcr.io/dev-cai/nora-api@sha256:{'5' * 64}",
        "web_image": f"ghcr.io/dev-cai/nora-web@sha256:{'6' * 64}",
        "migration_revision": "0022_interview_cases",
        "environment_file": str(target_env),
        "operation": "deploy",
        "recorded_at": "2026-08-15T00:00:00Z",
    }
    (target_dir / "result.json").write_text(json.dumps(target), encoding="utf-8")
    (state_dir / "current.json").write_text(json.dumps(current), encoding="utf-8")

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        if any(value.endswith("public_smoke.py") for value in arguments):
            assert json.loads((state_dir / "current.json").read_text()) == current
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    manager = ReleaseManager(
        env_file=env_file,
        state_dir=state_dir,
        backup_destination=tmp_path / "backup",
        script_dir=DEPLOY_DIR,
        run_command=run,
        free_bytes=lambda _path: RELEASE_MODULE.MIN_FREE_BYTES,
    )

    with pytest.raises(subprocess.CalledProcessError):
        manager.rollback(target_id, "operator request")

    assert json.loads((state_dir / "current.json").read_text()) == current
    assert list(state_dir.glob("rollback-*")) == []


def test_beta_workflow_uses_one_environment_locked_host_entrypoint() -> None:
    workflow = (ROOT / ".github/workflows/beta-deploy.yml").read_text(encoding="utf-8")
    assert "group: beta-deployment" in workflow
    assert workflow.count("environment: beta") == 2
    assert workflow.count("/usr/local/sbin/nora-release") == 2
    assert "nora-beta-deploy" in workflow
    assert "Jenkins" not in workflow
    assert "docker compose" not in workflow.split("runs-on: [self-hosted", 1)[1]


def test_release_installation_fixes_root_ownership_and_minimal_sudo_entrypoint() -> None:
    installer = (DEPLOY_DIR / "install_release_entrypoint.sh").read_text(encoding="utf-8")
    wrapper = (DEPLOY_DIR / "release.sh").read_text(encoding="utf-8")
    assert "install -o root -g root" in installer
    assert "/etc/sudoers.d/nora-release" in installer
    assert "visudo -cf" in installer
    assert "docker compose" not in installer
    assert "public_smoke.py" in installer
    assert "Caddyfile" not in installer
    assert "exec python /opt/nora/deploy/release.py" in wrapper
