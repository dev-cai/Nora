"""Execute the fixed D-019 Beta deployment and rollback state machine."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from preflight import read_environment
from release_manifest import ReleaseManifest, load_manifest, load_schema_compatibility
from verify_release_ci import load_check_runs, successful_check_run_ids

MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
RELEASE_ID_PATTERN = re.compile(r"[0-9a-f]{12}-[1-9][0-9]*")
RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class ReleaseFailure(RuntimeError):
    pass


class ReleaseManager:
    def __init__(
        self,
        *,
        env_file: Path,
        state_dir: Path,
        backup_destination: Path,
        script_dir: Path,
        run_command: RunCommand | None = None,
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self.env_file = env_file
        self.state_dir = state_dir
        self.backup_destination = backup_destination
        self.script_dir = script_dir
        self.run_command = run_command or self._run
        self.free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    def deploy(self, manifest_path: Path) -> None:
        manifest = load_manifest(manifest_path)
        with self._lock():
            self._validate_control_paths()
            release_dir = self.state_dir / manifest.release_id
            if release_dir.exists():
                raise ReleaseFailure("release_id already exists")
            release_dir.mkdir(parents=True, mode=0o700)
            candidate_env = release_dir / "production.env"
            self._write_candidate_environment(candidate_env, manifest)
            self._write_json(release_dir / "manifest.json", asdict(manifest))
            current = self._load_pointer("last-healthy.json")
            migrated = False
            candidate_runtime_active = False
            phase = "preflight"
            try:
                self._event(release_dir, phase, "started")
                self._preflight(candidate_env)
                self._event(release_dir, phase, "passed")

                phase = "backup"
                if (
                    current is not None
                    and current["migration_revision"] != manifest.migration_revision
                ):
                    self._event(release_dir, phase, "started")
                    self._command(
                        self.script_dir / "backup.sh",
                        self.env_file,
                        self.backup_destination,
                    )
                    self._event(release_dir, phase, "passed")
                else:
                    self._event(release_dir, phase, "skipped")

                phase = "pull"
                self._event(release_dir, phase, "started")
                self._compose(candidate_env, "pull", "api", "web", "migration")
                self._event(release_dir, phase, "passed")

                phase = "migrate"
                self._event(release_dir, phase, "started")
                self._stop_runtime(candidate_env)
                self._compose(candidate_env, "--profile", "initialize", "run", "--rm", "migration")
                self._compose(candidate_env, "--profile", "initialize", "run", "--rm", "db-init")
                self._compose(
                    candidate_env, "--profile", "initialize", "run", "--rm", "storage-init"
                )
                migrated = True
                self._event(release_dir, phase, "passed")

                phase = "start"
                self._event(release_dir, phase, "started")
                candidate_runtime_active = True
                self._start_and_wait(candidate_env)
                self._event(release_dir, phase, "passed")

                phase = "internal-smoke"
                self._event(release_dir, phase, "started")
                self._internal_smoke(candidate_env)
                self._event(release_dir, phase, "passed")

                phase = "public-smoke"
                self._event(release_dir, phase, "started")
                self._public_smoke(candidate_env)
                self._event(release_dir, phase, "passed")

                phase = "promote"
                self._event(release_dir, phase, "started")
                self._replace_environment(candidate_env)
                pointer = self._release_pointer(manifest, release_dir, operation="deploy")
                self._write_json(self.state_dir / "last-healthy.json", pointer)
                self._write_json(self.state_dir / "current.json", pointer)
                self._event(release_dir, phase, "passed")
                self._write_json(release_dir / "result.json", {"status": "healthy", **pointer})
            except Exception as exc:
                self._event(release_dir, phase, "failed", error=type(exc).__name__)
                self._write_json(
                    release_dir / "result.json",
                    {"status": "failed", "phase": phase, "error": type(exc).__name__},
                )
                rollback_allowed = (
                    migrated
                    and candidate_runtime_active
                    and current is not None
                    and (
                        current["migration_revision"] == manifest.migration_revision
                        or manifest.previous_schema_compatible
                    )
                )
                if rollback_allowed:
                    try:
                        self._rollback_to_pointer(current, reason=f"automatic-{phase}-failure")
                    except Exception as rollback_error:
                        self._stop_runtime(candidate_env)
                        raise ReleaseFailure("automatic rollback failed") from rollback_error
                elif candidate_runtime_active:
                    self._stop_runtime(candidate_env)
                raise

    def rollback(self, release_id: str, reason: str) -> None:
        if RELEASE_ID_PATTERN.fullmatch(release_id) is None:
            raise ReleaseFailure("rollback release_id is invalid")
        normalized_reason = " ".join(reason.split())
        if not normalized_reason or len(normalized_reason) > 500:
            raise ReleaseFailure("rollback reason must contain 1-500 characters")
        with self._lock():
            self._validate_control_paths()
            target_result = self._read_json(self.state_dir / release_id / "result.json")
            current = self._load_pointer("current.json")
            if target_result.get("status") != "healthy" or current is None:
                raise ReleaseFailure("rollback target must be a known healthy release")
            if target_result["migration_revision"] != current["migration_revision"]:
                raise ReleaseFailure("rollback across Schema revisions requires isolated restore")
            self._rollback_to_pointer(target_result, reason=normalized_reason)

    def _preflight(self, candidate_env: Path) -> None:
        if self.free_bytes(self.state_dir) < MIN_FREE_BYTES:
            raise ReleaseFailure("release state filesystem has less than 2 GiB free")
        self._command(sys.executable, self.script_dir / "preflight.py", "--env-file", candidate_env)
        self._command(
            "docker",
            "compose",
            "--env-file",
            candidate_env,
            "-f",
            self.script_dir / "compose.production.yml",
            "config",
            "--quiet",
        )

    def _validate_control_paths(self) -> None:
        for path, kind in ((self.env_file, "file"), (self.state_dir, "directory")):
            details = path.lstat()
            valid_type = path.is_file() if kind == "file" else path.is_dir()
            if path.is_symlink() or not valid_type:
                raise ReleaseFailure(f"release control {kind} must be a regular non-symlink")
            if os.geteuid() == 0 and details.st_uid != 0:
                raise ReleaseFailure(f"release control {kind} must be root-owned")
            if details.st_mode & 0o007:
                raise ReleaseFailure(f"release control {kind} must not be accessible by others")

    def _start_and_wait(self, env_file: Path) -> None:
        self._compose(
            env_file,
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "120",
            "db",
            "storage",
            "api",
            "web",
        )
        self._compose(
            env_file,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=5)",
        )
        self._compose(
            env_file,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5)",
        )

    def _internal_smoke(self, env_file: Path) -> None:
        self._compose(env_file, "exec", "-T", "api", "python", "scripts/beta_api_smoke.py")
        self._compose(
            env_file, "exec", "-T", "web", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:5173/"
        )
        self._compose(env_file, "exec", "-T", "api", "python", "scripts/artifact_storage_smoke.py")

    def _public_smoke(self, env_file: Path) -> None:
        values = read_environment(env_file)
        try:
            origin = values["NORA_PUBLIC_ORIGIN"]
        except KeyError as exc:
            raise ReleaseFailure("production environment is missing NORA_PUBLIC_ORIGIN") from exc
        self._command(sys.executable, self.script_dir / "public_smoke.py", "--origin", origin)

    def _stop_runtime(self, env_file: Path) -> None:
        self._compose(env_file, "stop", "web", "api")

    def _rollback_to_pointer(self, target: dict[str, object], *, reason: str) -> None:
        target_env = Path(str(target["environment_file"]))
        self._stop_runtime(target_env)
        try:
            self._start_and_wait(target_env)
            self._internal_smoke(target_env)
            self._public_smoke(target_env)
        except Exception:
            self._stop_runtime(target_env)
            raise
        self._replace_environment(target_env)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rollback_dir = self.state_dir / f"rollback-{timestamp}"
        rollback_dir.mkdir(mode=0o700)
        record = {
            **target,
            "status": "healthy",
            "operation": "rollback",
            "reason": reason,
            "recorded_at": _now(),
        }
        self._write_json(rollback_dir / "result.json", record)
        self._write_json(self.state_dir / "last-healthy.json", record)
        self._write_json(self.state_dir / "current.json", record)

    def _write_candidate_environment(self, output: Path, manifest: ReleaseManifest) -> None:
        values = self.env_file.read_text(encoding="utf-8").splitlines()
        replacements = {"NORA_API_IMAGE": manifest.api_image, "NORA_WEB_IMAGE": manifest.web_image}
        seen: set[str] = set()
        rewritten: list[str] = []
        for line in values:
            name = line.split("=", 1)[0].strip() if "=" in line else ""
            if name in replacements:
                rewritten.append(f"{name}={replacements[name]}")
                seen.add(name)
            else:
                rewritten.append(line)
        if seen != set(replacements):
            raise ReleaseFailure("production environment is missing image variables")
        output.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
        os.chmod(output, 0o600)

    def _replace_environment(self, candidate: Path) -> None:
        temporary = self.env_file.with_name(f".{self.env_file.name}.release")
        shutil.copyfile(candidate, temporary)
        os.chmod(temporary, self.env_file.stat().st_mode & 0o777)
        os.chown(temporary, self.env_file.stat().st_uid, self.env_file.stat().st_gid)
        os.replace(temporary, self.env_file)

    def _release_pointer(
        self, manifest: ReleaseManifest, release_dir: Path, *, operation: str
    ) -> dict[str, object]:
        return {
            "release_id": manifest.release_id,
            "commit_sha": manifest.commit_sha,
            "workflow_run_id": manifest.workflow_run_id,
            "api_image": manifest.api_image,
            "web_image": manifest.web_image,
            "migration_revision": manifest.migration_revision,
            "environment_file": str(release_dir / "production.env"),
            "operation": operation,
            "recorded_at": _now(),
        }

    def _compose(self, env_file: Path, *arguments: str) -> None:
        self._command(
            "docker",
            "compose",
            "--env-file",
            env_file,
            "-f",
            self.script_dir / "compose.production.yml",
            *arguments,
        )

    def _command(self, *arguments: object) -> None:
        self.run_command([str(value) for value in arguments])

    @staticmethod
    def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(arguments, check=True, text=True, capture_output=False)

    def _event(
        self, release_dir: Path, phase: str, status: str, *, error: str | None = None
    ) -> None:
        value = {"phase": phase, "status": status, "recorded_at": _now()}
        if error is not None:
            value["error"] = error
        with (release_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")

    def _load_pointer(self, name: str) -> dict[str, object] | None:
        path = self.state_dir / name
        return None if not path.exists() else self._read_json(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ReleaseFailure("release state must be a JSON object")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _lock(self):  # type: ignore[no-untyped-def]
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = (self.state_dir / "deployment.lock").open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise ReleaseFailure("another deployment or rollback holds the host lock") from exc

        class Lock:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *_args: object) -> None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

        return Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def verify_release_bundle(manifest_path: Path, manifest: ReleaseManifest) -> None:
    expected = {
        "sbom-api.spdx.json": manifest.api_sbom_sha256,
        "sbom-web.spdx.json": manifest.web_sbom_sha256,
        "schema-compatibility.json": manifest.schema_policy_sha256,
    }
    for name, digest in expected.items():
        path = manifest_path.parent / name
        details = path.lstat()
        if path.is_symlink() or not path.is_file() or details.st_size > 64 * 1024 * 1024:
            raise ReleaseFailure("release SBOM must be a bounded regular non-symlink file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ReleaseFailure("release evidence digest does not match the manifest")
    compatible = load_schema_compatibility(
        manifest_path.parent / "schema-compatibility.json", manifest.migration_revision
    )
    if compatible is not manifest.previous_schema_compatible:
        raise ReleaseFailure("Schema compatibility policy does not match the manifest")


def verify_github_evidence(manifest: ReleaseManifest, token: str) -> None:
    observed = successful_check_run_ids(
        load_check_runs(manifest.repository, manifest.commit_sha, token)
    )
    if observed != manifest.ci_check_run_ids:
        raise ReleaseFailure("main CI check evidence changed or does not match the manifest")
    environment = {**os.environ, "GH_TOKEN": token}
    for image in (manifest.api_image, manifest.web_image):
        subprocess.run(
            ["gh", "attestation", "verify", f"oci://{image}", "--repo", manifest.repository],
            check=True,
            text=True,
            stdout=subprocess.DEVNULL,
            env=environment,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--backup-destination", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("manifest", type=Path)
    deploy.add_argument("registry_username")
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("release_id")
    rollback.add_argument("reason")
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("release_error=entrypoint must run as root")
    manager = ReleaseManager(
        env_file=arguments.env_file,
        state_dir=arguments.state_dir,
        backup_destination=arguments.backup_destination,
        script_dir=Path(__file__).resolve().parent,
    )
    try:
        if arguments.command == "deploy":
            registry_token = sys.stdin.read()
            if not registry_token or len(registry_token) > 4096:
                raise ReleaseFailure("registry token must contain 1-4096 characters")
            manifest = load_manifest(arguments.manifest)
            verify_release_bundle(arguments.manifest, manifest)
            verify_github_evidence(manifest, registry_token)
            subprocess.run(
                [
                    "docker",
                    "login",
                    "ghcr.io",
                    "--username",
                    arguments.registry_username,
                    "--password-stdin",
                ],
                check=True,
                text=True,
                input=registry_token,
            )
            try:
                manager.deploy(arguments.manifest)
            finally:
                subprocess.run(
                    ["docker", "logout", "ghcr.io"],
                    check=False,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        else:
            manager.rollback(arguments.release_id, arguments.reason)
    except (OSError, ValueError, ReleaseFailure, subprocess.CalledProcessError) as exc:
        print(f"release_error={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
