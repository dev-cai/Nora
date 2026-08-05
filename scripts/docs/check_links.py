#!/usr/bin/env python3
"""Check relative Markdown links (files and GitHub anchors) across the repo.

Usage: python scripts/docs/check_links.py

Walks repo root ``*.md``, ``docs/**/*.md`` and ``.codex/skills/*/SKILL.md``.
For every inline relative link ``[text](path[#anchor])`` it verifies the
target file exists and that the ``#anchor`` (if any) matches a heading slug.
Exits non-zero on any broken link. External URLs, ``mailto:``, fragment-only
links, and links inside fenced code blocks / inline code are ignored.

Uses only the Python standard library so it can run from the ``tools``
container or directly in CI without new dependencies.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Root markdown files scanned directly; directories scanned recursively.
SCAN_FILES = ("README.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md")
SCAN_DIRS = ("docs",)
SCAN_SKILL_PATTERN = ".codex/skills/*/SKILL.md"
SKIP_DIRS = {"node_modules", ".git"}

FENCE = re.compile(r"^```|^~~~")
INLINE_CODE = re.compile(r"`[^`]*`")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|mailto:|tel:)", re.IGNORECASE)

_slug_cache: dict[Path, set[str]] = {}


def slugify(text: str) -> str:
    """Approximate GitHub's heading anchor slug rules.

    Lowercase; drop characters that are not letters/digits/underscore/space/
    hyphen; then collapse runs of whitespace to a single hyphen.
    """
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = re.sub(r"[^\w\s-]", "", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", "-", cleaned.strip()).lower()


def heading_slugs(path: Path) -> set[str]:
    if path in _slug_cache:
        return _slug_cache[path]
    slugs: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _slug_cache[path] = slugs
        return slugs
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            slugs.add(slugify(m.group(1).strip()))
    _slug_cache[path] = slugs
    return slugs


def iter_md_files() -> list[Path]:
    files = [ROOT / f for f in SCAN_FILES if (ROOT / f).exists()]
    for d in SCAN_DIRS:
        base = ROOT / d
        if base.is_dir():
            files.extend(
                p for p in base.rglob("*.md")
                if not any(part in SKIP_DIRS for part in p.parts)
            )
    skills = ROOT.glob(SCAN_SKILL_PATTERN)
    files.extend(skills)
    return files


def main() -> int:
    errors: list[str] = []
    for md in iter_md_files():
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            errors.append(f"{md.relative_to(ROOT)}: cannot read: {exc}")
            continue
        in_fence = False
        for lineno, line in enumerate(lines, start=1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = INLINE_CODE.sub("", line)
            for url in LINK.findall(line):
                url = url.strip()
                if not url or EXTERNAL.match(url) or url.startswith("#"):
                    continue
                target_file, _, anchor = url.partition("#")
                if not target_file:
                    continue
                target = (md.parent / target_file).resolve()
                if not target.is_file():
                    errors.append(
                        f"{md.relative_to(ROOT)}:{lineno}: "
                        f"target file missing: {url}"
                    )
                    continue
                if anchor:
                    slugs = heading_slugs(target)
                    if slugify(anchor) not in slugs:
                        errors.append(
                            f"{md.relative_to(ROOT)}:{lineno}: "
                            f"anchor not found: {url} "
                            f"(in {target.relative_to(ROOT)})"
                        )
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"\n{len(errors)} broken link(s) found.", file=sys.stderr)
        return 1
    print("All relative Markdown links are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
