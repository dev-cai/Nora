"""Verify the protected Beta Environment and dedicated deployment Runner."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request

REQUIRED_RUNNER_LABELS = {"self-hosted", "linux", "x64", "nora-beta-deploy"}


def validate_environment(value: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if value.get("name") != "beta":
        errors.append("protected beta Environment is missing")
    rules = value.get("protection_rules")
    if not isinstance(rules, list):
        errors.append("beta Environment protection rules are missing")
        rules = []
    reviewers = [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and rule.get("type") == "required_reviewers"
        and isinstance(rule.get("reviewers"), list)
        and rule["reviewers"]
    ]
    if not reviewers:
        errors.append("beta Environment must require an explicit reviewer")
    policy = value.get("deployment_branch_policy")
    if not isinstance(policy, dict) or policy.get("protected_branches") is not True:
        errors.append("beta Environment must restrict deployments to protected branches")
    if value.get("can_admins_bypass") is not False:
        errors.append("beta Environment must disable administrator bypass")
    return errors


def validate_runners(values: list[dict[str, object]]) -> list[str]:
    for runner in values:
        labels = runner.get("labels")
        if runner.get("status") != "online" or not isinstance(labels, list):
            continue
        names = {
            str(label.get("name"))
            for label in labels
            if isinstance(label, dict) and label.get("name")
        }
        if REQUIRED_RUNNER_LABELS <= names:
            return []
    return ["an online dedicated nora-beta-deploy Runner is required"]


def load_json(repository: str, path: str, token: str) -> object:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="dev-cai/Nora")
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("release_control_error=GITHUB_TOKEN is required")
    try:
        environment = load_json(
            arguments.repository,
            f"environments/{urllib.parse.quote('beta', safe='')}",
            token,
        )
        runners_payload = load_json(arguments.repository, "actions/runners?per_page=100", token)
        if not isinstance(environment, dict) or not isinstance(runners_payload, dict):
            raise ValueError("GitHub release-control response is invalid")
        runners = runners_payload.get("runners")
        if not isinstance(runners, list):
            raise ValueError("GitHub Runner response is invalid")
        errors = validate_environment(environment) + validate_runners(
            [runner for runner in runners if isinstance(runner, dict)]
        )
    except (OSError, urllib.error.HTTPError, ValueError) as exc:
        print(f"release_control_error={type(exc).__name__}")
        raise SystemExit(2) from exc
    if errors:
        for error in errors:
            print(f"release_control_error={error}")
        raise SystemExit(2)
    print("release_control=passed")


if __name__ == "__main__":
    main()
