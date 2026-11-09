#!/usr/bin/env python3
"""Flag references whose recorded verification date needs refreshing."""

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from check_jobs import CHINA


SOURCE_ROW = re.compile(r"^\| \[([^\]]+)\]\((https://[^ )]+)\) \| [^|]+ \| ([^|]+?) \|$")
LINK = re.compile(r"https?://[^\s<>()]+")
VERIFIED_ON = re.compile(r"核验(?:时间\s*[:：]?|于)\s*(\d{4}-\d{2}-\d{2})(?![\d-])")
NAVIGATION_ONLY = "仅导航，不追踪日期"
NEEDS_CHECK = "需重新核对"
MAX_AGE_DAYS = 30
REFERENCE_MAX_AGE_DAYS = 90


def age_days(verified, today):
    age = (today - date.fromisoformat(verified)).days
    if age < 0:
        raise ValueError(f"核验日期在未来（{verified}）")
    return age


def source_rows(markdown, today):
    found = False
    for number, line in enumerate(markdown.splitlines(), start=1):
        if not line.startswith("| ["):
            continue
        match = SOURCE_ROW.fullmatch(line)
        if not match:
            raise ValueError(f"第 {number} 行须含官方入口链接、用途和 last_verified")
        found = True
        label, _, verified = match.groups()
        if verified == NAVIGATION_ONLY:
            continue
        status = "导航日期有效"
        if verified == "—" or age_days(verified, today) > MAX_AGE_DAYS:
            status = NEEDS_CHECK
        yield number, label, status, verified
    if not found:
        raise ValueError("未读取到官方入口")


def source_status(markdown, today):
    return [(label, status, verified) for _, label, status, verified in source_rows(markdown, today)]


def dated_links(path, today, max_age_days):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not LINK.search(line):
            continue
        for verified in dict.fromkeys(VERIFIED_ON.findall(line)):
            try:
                age = age_days(verified, today)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: {error}") from error
            if age > max_age_days:
                yield number, verified


def display_path(path):
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="?", default=(
        Path(__file__).resolve().parents[1] / "references" / "official-sources.md"
    ))
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--max-age-days", type=int, default=REFERENCE_MAX_AGE_DAYS,
                        help="Maximum age of dated links outside the navigation table (default: 90)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any entry needs a recheck")
    args = parser.parse_args()
    if args.max_age_days < 0:
        parser.error("--max-age-days must be non-negative")
    today = args.as_of or datetime.now(CHINA).date()
    sources = args.sources.resolve()
    stale = False
    try:
        for number, label, status, verified in source_rows(sources.read_text(encoding="utf-8"), today):
            location = f"\t{display_path(sources)}:{number}" if status == NEEDS_CHECK else ""
            print(f"{label}\t{status}\t{verified}{location}")
            stale |= status == NEEDS_CHECK
        for path in sorted(sources.parent.rglob("*.md")):
            if path == sources:
                continue
            for number, verified in dated_links(path, today, args.max_age_days):
                print(f"{display_path(path)}:{number}\t{NEEDS_CHECK}\t{verified}")
                stale = True
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    if args.strict and stale:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
