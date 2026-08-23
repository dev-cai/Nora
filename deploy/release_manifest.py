"""Create and validate immutable Beta release manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
REVISION_PATTERN = re.compile(r"[a-zA-Z0-9_]{1,64}")
IMAGE_PATTERN = re.compile(r"ghcr\.io/dev-cai/nora-(?:api|web)@sha256:(?P<digest>[0-9a-f]{64})")
ATTESTATION_PATTERN = re.compile(r"https://github\.com/dev-cai/Nora/attestations/[0-9]+")
MAX_MANIFEST_BYTES = 16 * 1024
REQUIRED_CI_CHECKS = {
    "Code quality and tests",
    "Container configuration and builds",
    "Documentation quality gate",
    "Frontend quality gate",
    "Secret, dependency, SBOM, and vulnerability gates",
}


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    format_version: int
    release_id: str
    repository: str
    source_ref: str
    commit_sha: str
    workflow_run_id: int
    ci_check_run_ids: dict[str, int]
    api_image: str
    web_image: str
    api_sbom_sha256: str
    web_sbom_sha256: str
    api_attestation_url: str
    web_attestation_url: str
    migration_revision: str
    schema_policy_sha256: str
    previous_schema_compatible: bool
    created_at: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ReleaseManifest":
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            raise ValueError("release manifest fields are incomplete or unknown")
        manifest = cls(**value)  # type: ignore[arg-type]
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.format_version != 1:
            raise ValueError("release manifest format_version must be 1")
        if self.repository != "dev-cai/Nora" or self.source_ref != "refs/heads/main":
            raise ValueError("release manifest must originate from protected Nora main")
        if COMMIT_PATTERN.fullmatch(self.commit_sha) is None:
            raise ValueError("release manifest commit_sha must be a lowercase full SHA")
        expected_release_id = f"{self.commit_sha[:12]}-{self.workflow_run_id}"
        if self.release_id != expected_release_id:
            raise ValueError("release_id must bind the commit and workflow run")
        if self.workflow_run_id < 1:
            raise ValueError("workflow_run_id must be positive")
        if set(self.ci_check_run_ids) != REQUIRED_CI_CHECKS or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in self.ci_check_run_ids.values()
        ):
            raise ValueError("ci_check_run_ids must bind every required successful main check")
        for name, image, component in (
            ("api_image", self.api_image, "api"),
            ("web_image", self.web_image, "web"),
        ):
            match = IMAGE_PATTERN.fullmatch(image)
            if match is None or f"nora-{component}@" not in image:
                raise ValueError(f"{name} must be a Nora GHCR image pinned by digest")
        for name, digest in (
            ("api_sbom_sha256", self.api_sbom_sha256),
            ("web_sbom_sha256", self.web_sbom_sha256),
        ):
            if SHA256_PATTERN.fullmatch(digest) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256")
        for name, url in (
            ("api_attestation_url", self.api_attestation_url),
            ("web_attestation_url", self.web_attestation_url),
        ):
            if ATTESTATION_PATTERN.fullmatch(url) is None:
                raise ValueError(f"{name} must identify a Nora GitHub attestation")
        if REVISION_PATTERN.fullmatch(self.migration_revision) is None:
            raise ValueError("migration_revision is invalid")
        if SHA256_PATTERN.fullmatch(self.schema_policy_sha256) is None:
            raise ValueError("schema_policy_sha256 must be a lowercase SHA-256")
        if not isinstance(self.previous_schema_compatible, bool):
            raise ValueError("previous_schema_compatible must be boolean")
        try:
            created_at = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO-8601 timestamp") from exc
        if created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def load_manifest(path: Path) -> ReleaseManifest:
    details = path.lstat()
    if path.is_symlink() or not path.is_file() or details.st_size > MAX_MANIFEST_BYTES:
        raise ValueError("release manifest must be a small regular non-symlink file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release manifest must be a JSON object")
    return ReleaseManifest.from_dict(value)


def load_schema_compatibility(path: Path, revision: str) -> bool:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"format_version", "revisions"}:
        raise ValueError("Schema compatibility policy is invalid")
    if value["format_version"] != 1 or not isinstance(value["revisions"], dict):
        raise ValueError("Schema compatibility policy is invalid")
    revisions = value["revisions"]
    entry = revisions.get(revision)
    if not isinstance(entry, dict) or set(entry) != {"previous_schema_compatible", "reason"}:
        raise ValueError("migration revision is missing from Schema compatibility policy")
    compatible = entry["previous_schema_compatible"]
    reason = entry["reason"]
    if not isinstance(compatible, bool) or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Schema compatibility policy entry is invalid")
    return compatible


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("manifest", type=Path)

    create = subparsers.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--commit-sha", required=True)
    create.add_argument("--workflow-run-id", type=int, required=True)
    create.add_argument("--ci-check-runs", type=Path, required=True)
    create.add_argument("--api-image", required=True)
    create.add_argument("--web-image", required=True)
    create.add_argument("--api-sbom-sha256", required=True)
    create.add_argument("--web-sbom-sha256", required=True)
    create.add_argument("--api-attestation-url", required=True)
    create.add_argument("--web-attestation-url", required=True)
    create.add_argument("--migration-revision", required=True)
    create.add_argument("--schema-compatibility-policy", type=Path, required=True)
    arguments = parser.parse_args()

    if arguments.command == "validate":
        manifest = load_manifest(arguments.manifest)
        print(f"release_manifest=valid release_id={manifest.release_id}")
        return

    ci_check_run_ids = json.loads(arguments.ci_check_runs.read_text(encoding="utf-8"))
    if not isinstance(ci_check_run_ids, dict):
        raise SystemExit("ci_check_run_ids must be a JSON object")
    policy_bytes = arguments.schema_compatibility_policy.read_bytes()
    manifest = ReleaseManifest(
        format_version=1,
        release_id=f"{arguments.commit_sha[:12]}-{arguments.workflow_run_id}",
        repository="dev-cai/Nora",
        source_ref="refs/heads/main",
        commit_sha=arguments.commit_sha,
        workflow_run_id=arguments.workflow_run_id,
        ci_check_run_ids=ci_check_run_ids,
        api_image=arguments.api_image,
        web_image=arguments.web_image,
        api_sbom_sha256=arguments.api_sbom_sha256,
        web_sbom_sha256=arguments.web_sbom_sha256,
        api_attestation_url=arguments.api_attestation_url,
        web_attestation_url=arguments.web_attestation_url,
        migration_revision=arguments.migration_revision,
        schema_policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
        previous_schema_compatible=load_schema_compatibility(
            arguments.schema_compatibility_policy, arguments.migration_revision
        ),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    manifest.validate()
    arguments.output.write_text(manifest.to_json() + "\n", encoding="utf-8")
    print(f"release_manifest=created release_id={manifest.release_id}")


if __name__ == "__main__":
    main()
