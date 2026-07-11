#!/usr/bin/env python3
"""Check local Markdown links used by the README and research note."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def github_anchor(heading: str) -> str:
    anchor = heading.strip().lower()
    anchor = re.sub(r"`([^`]*)`", r"\1", anchor)
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor


def anchors_for(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip()
        if heading:
            anchors.add(github_anchor(heading))
    return anchors


def extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " " in target:
        target = target.split(" ", 1)[0]
    return target


def is_external(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https", "mailto"}


def check_file(path: Path, repo_root: Path) -> tuple[int, list[str]]:
    checked = 0
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    for match in LINK_RE.finditer(text):
        raw_target = match.group(1)
        target = extract_target(raw_target)
        if not target or is_external(target):
            continue

        checked += 1
        target_path_text, _, fragment = target.partition("#")
        if target_path_text:
            resolved = (path.parent / unquote(target_path_text)).resolve()
        else:
            resolved = path.resolve()

        try:
            resolved.relative_to(repo_root)
        except ValueError:
            errors.append(f"{path}: link escapes repository: {raw_target}")
            continue

        if not resolved.exists():
            errors.append(f"{path}: missing link target: {raw_target}")
            continue

        if fragment and resolved.suffix.lower() == ".md":
            anchor = unquote(fragment).lower()
            if anchor not in anchors_for(resolved):
                errors.append(f"{path}: missing anchor #{fragment} in {resolved}")

    return checked, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        default=["README.md", "docs/research_note.md"],
        help="Markdown files to check, relative to the repository root.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    total_checked = 0
    all_errors: list[str] = []

    for path_text in args.paths:
        path = (repo_root / path_text).resolve()
        if not path.exists():
            all_errors.append(f"missing markdown file: {path_text}")
            continue
        checked, errors = check_file(path, repo_root)
        total_checked += checked
        all_errors.extend(errors)

    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        print(f"checked {total_checked} local markdown links; {len(all_errors)} failed", file=sys.stderr)
        return 1

    print(f"checked {total_checked} local markdown links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
