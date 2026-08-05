#!/usr/bin/env python3
"""Check the document source-of-truth contract.

Verifies:
1. Every file referenced in PRODUCT_VISION.md §9 (the document
   source-of-truth table) exists, including allowed-summary targets.
2. Every file referenced in README.md's "文档" section (role navigation
   and the full index) exists.

This complements check_links.py by giving targeted diagnostics for the
document index contract. Uses only the Python standard library.

Usage: python scripts/docs/check_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_VISION = ROOT / "docs" / "PRODUCT_VISION.md"
README = ROOT / "README.md"

HEADING = re.compile(r"^(#{1,6})\s+")
LINK = re.compile(r"\]\(([^)]+)\)")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|mailto:|tel:)", re.IGNORECASE)


def extract_section_links(path: Path, section: str) -> list[str]:
    """Return relative link targets found under the given section heading.

    The section ends at the next heading of the same or shallower level.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    start: int | None = None
    level: int | None = None
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        h = len(m.group(1))
        if start is None:
            if section in line:
                start, level = i, h
        elif h <= level:
            lines = lines[:i]
            break
    if start is None:
        return []
    urls: list[str] = []
    for line in lines[start:]:
        for url in LINK.findall(line):
            if EXTERNAL.match(url) or url.startswith("#") or url.startswith(
                "!"
            ):
                continue
            urls.append(url.split("#")[0])
    return urls


def check(path: Path, urls: list[str]) -> list[str]:
    errors: list[str] = []
    for url in urls:
        target = (path.parent / url).resolve()
        if not target.is_file():
            errors.append(f"{path.relative_to(ROOT)}: referenced file missing: {url}")
    return errors


def main() -> int:
    errors: list[str] = []
    if PRODUCT_VISION.is_file():
        errors += check(PRODUCT_VISION, extract_section_links(PRODUCT_VISION, "文档真源"))
    if README.is_file():
        errors += check(README, extract_section_links(README, "文档"))
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"\n{len(errors)} consistency error(s).", file=sys.stderr)
        return 1
    print("Document source-of-truth references are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
