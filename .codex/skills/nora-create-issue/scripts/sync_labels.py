#!/usr/bin/env python3
"""Check or synchronize Nora's managed GitHub labels."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def run_gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout


def root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_config() -> dict[str, Any]:
    return json.loads((root() / ".github" / "labels.json").read_text(encoding="utf-8"))


def repository() -> str:
    return run_gh(
        "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"
    ).strip()


def actual_labels(repo: str) -> dict[str, dict[str, str]]:
    items = json.loads(
        run_gh(
            "label",
            "list",
            "--repo",
            repo,
            "--limit",
            "200",
            "--json",
            "name,color,description",
        )
    )
    return {item["name"]: item for item in items}


def drift(config: dict[str, Any], actual: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for expected in config["labels"]:
        current = actual.get(expected["name"])
        if current is None:
            errors.append(f"missing: {expected['name']}")
        elif (
            current["color"].lower() != expected["color"].lower()
            or current.get("description", "") != expected["description"]
        ):
            errors.append(f"drift: {expected['name']}")
    for name in config["forbidden_labels"]:
        if name in actual:
            errors.append(f"forbidden: {name}")
    return errors


def apply(config: dict[str, Any], repo: str) -> None:
    for label in config["labels"]:
        run_gh(
            "label",
            "create",
            label["name"],
            "--repo",
            repo,
            "--color",
            label["color"],
            "--description",
            label["description"],
            "--force",
        )
    current = actual_labels(repo)
    for name in config["forbidden_labels"]:
        if name in current:
            run_gh("label", "delete", name, "--repo", repo, "--yes")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = load_config()
    repo = repository()
    if args.apply:
        apply(config, repo)
    errors = drift(config, actual_labels(repo))
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Labels are synchronized for {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
