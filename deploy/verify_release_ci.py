"""Verify that a protected main Commit passed every Nora release gate."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

from release_manifest import REQUIRED_CI_CHECKS


def successful_check_run_ids(check_runs: list[dict[str, object]]) -> dict[str, int]:
    latest: dict[str, dict[str, object]] = {}
    for check in check_runs:
        name = check.get("name")
        if name not in REQUIRED_CI_CHECKS:
            continue
        check_id = check.get("id")
        if isinstance(check_id, bool) or not isinstance(check_id, int) or check_id < 1:
            raise ValueError(f"required CI check has no stable id: {name}")
        previous = latest.get(str(name))
        previous_id = None if previous is None else previous.get("id")
        if previous_id is not None and (
            isinstance(previous_id, bool) or not isinstance(previous_id, int)
        ):
            raise ValueError(f"required CI check has no stable id: {name}")
        if previous_id is None or check_id > previous_id:
            latest[str(name)] = check
    missing = REQUIRED_CI_CHECKS - set(latest)
    if missing:
        raise ValueError(f"required CI checks are missing: {', '.join(sorted(missing))}")
    found: dict[str, int] = {}
    for name, check in latest.items():
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            raise ValueError(f"required CI check is not successful: {name}")
        check_id = check.get("id")
        if isinstance(check_id, bool) or not isinstance(check_id, int):
            raise ValueError(f"required CI check has no stable id: {name}")
        found[name] = check_id
    return found


def load_check_runs(repository: str, commit_sha: str, token: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/commits/{commit_sha}/check-runs?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    check_runs = payload.get("check_runs")
    if not isinstance(check_runs, list):
        raise ValueError("GitHub check-runs response is invalid")
    return [value for value in check_runs if isinstance(value, dict)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="dev-cai/Nora")
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("release_ci_error=GITHUB_TOKEN is required")
    try:
        result = successful_check_run_ids(
            load_check_runs(arguments.repository, arguments.commit_sha, token)
        )
    except (OSError, ValueError) as exc:
        print(f"release_ci_error={exc}")
        raise SystemExit(2) from exc
    arguments.output.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("release_ci=passed")


if __name__ == "__main__":
    main()
