#!/usr/bin/env python3
"""Flag source navigation entries whose verification date needs refreshing."""

import argparse
import re
from datetime import date, datetime
from pathlib import Path

from check_jobs import CHINA


SOURCE_ROW = re.compile(r"^\| \[([^\]]+)\]\((https://[^ )]+)\) \| [^|]+ \| ([^|]+?) \|$")
MAX_AGE_DAYS = 30


def source_status(markdown, today):
    results = []
    for line in markdown.splitlines():
        if not line.startswith("| ["):
            continue
        match = SOURCE_ROW.fullmatch(line)
        if not match:
            raise ValueError("官方入口行须含链接、用途和 last_verified")
        label, _, verified = match.groups()
        if verified == "—":
            results.append((label, "需重新核对", verified))
            continue
        checked = date.fromisoformat(verified)
        age = (today - checked).days
        if age < 0:
            raise ValueError(f"{label} 的 last_verified 在未来")
        results.append((label, "需重新核对" if age > MAX_AGE_DAYS else "导航日期有效", verified))
    if not results:
        raise ValueError("未读取到官方入口")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="?", default=(
        Path(__file__).resolve().parents[1] / "references" / "official-sources.md"
    ))
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    today = args.as_of or datetime.now(CHINA).date()
    try:
        for label, status, verified in source_status(args.sources.read_text(encoding="utf-8"), today):
            print(f"{label}\t{status}\t{verified}")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
