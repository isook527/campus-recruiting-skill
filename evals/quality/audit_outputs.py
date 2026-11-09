#!/usr/bin/env python3
"""Audit output completeness without grading resume quality."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


LEAK_PATTERNS = [
    re.compile(r"\bv1\.[23]\.0\b", re.I),
    re.compile(r"\b(baseline|candidate|control|treatment)\b", re.I),
    re.compile(r"基线|候选版本|对照组|实验组"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--arm", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = json.loads(args.cases.read_text(encoding="utf-8"))
    expected = []
    for case in spec["cases"]:
        case_num = int(case["id"][1:])
        for run in range(1, spec["attempts_per_arm"] + 1):
            expected.append(f"q{case_num:02d}-r{run:02d}.md")

    actual = sorted(path.name for path in args.arm.glob("*.md") if path.name != "RUN-NOTES.md")
    errors = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        errors.append(f"missing: {', '.join(missing)}")
    if extra:
        errors.append(f"extra: {', '.join(extra)}")

    hashes: dict[str, list[str]] = {}
    for name in expected:
        path = args.arm / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            errors.append(f"empty: {name}")
            continue
        for pattern in LEAK_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible arm/version leak in {name}: {pattern.pattern}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        hashes.setdefault(digest, []).append(name)

    for names in hashes.values():
        if len(names) > 1:
            print(f"NOTE: exact duplicate outputs retained: {', '.join(names)}")

    if errors:
        print("AUDIT FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"AUDIT OK: {len(expected)} non-empty, unlabeled outputs")


if __name__ == "__main__":
    main()
