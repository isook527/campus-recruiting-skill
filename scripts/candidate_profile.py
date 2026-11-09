#!/usr/bin/env python3
"""Initialize or read a user-selected local campus recruiting profile."""

import argparse
import json
import math
import os
import re
from datetime import date
from pathlib import Path, PurePosixPath

from application_log import assert_no_sensitive


TEXT_FIELDS = {
    "education": ("school", "school_level", "first_degree", "highest_degree", "major",
                  "graduation_month", "gpa", "rank"),
    "qualifications": ("english", "political_status", "student_origin"),
}
PROFILE = {
    "schema_version": 1,
    **{section: dict.fromkeys(fields) for section, fields in TEXT_FIELDS.items()},
    "preferences": {"cities": [], "directions": [], "weekly_hours": None},
    "experience_ids": [],
    "fact_cards_file": None,
}
PROFILE["qualifications"]["certificates"] = []
MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")
FACT_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}\Z")


def validate(profile):
    assert_no_sensitive(profile)
    if not isinstance(profile, dict) or set(profile) != PROFILE.keys():
        raise ValueError("档案字段不符。请从 init 生成的模板开始。")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise ValueError("不支持的求职档案版本")
    for section in ("education", "qualifications", "preferences"):
        value = profile[section]
        if not isinstance(value, dict) or set(value) != PROFILE[section].keys():
            raise ValueError(f"{section} 字段不符")
    for section, fields in TEXT_FIELDS.items():
        for field in fields:
            value = profile[section][field]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field} 须为非空文本或 null")
    month = profile["education"]["graduation_month"]
    if month is not None:
        if not MONTH.fullmatch(month) or month.startswith("0000"):
            raise ValueError("graduation_month 须为 YYYY-MM")
        date.fromisoformat(month + "-01")
    source = profile["fact_cards_file"]
    if source is not None:
        if not isinstance(source, str) or not source.strip() or any(c in source for c in "\\:\n\r\0"):
            raise ValueError("fact_cards_file 须为档案目录内的相对文件路径")
        path = PurePosixPath(source)
        if not path.name or path.is_absolute() or ".." in path.parts:
            raise ValueError("fact_cards_file 须为档案目录内的相对文件路径")
    for name, values in (
        ("certificates", profile["qualifications"]["certificates"]),
        ("cities", profile["preferences"]["cities"]),
        ("directions", profile["preferences"]["directions"]),
        ("experience_ids", profile["experience_ids"]),
    ):
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"{name} 须为非空文本组成的数组或空数组")
    ids = profile["experience_ids"]
    if any(not FACT_ID.fullmatch(item) for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("经历只填不重复的事实卡编号")
    hours = profile["preferences"]["weekly_hours"]
    if hours is not None and (type(hours) not in {int, float} or not 0 <= hours <= 168 or not math.isfinite(hours)):
        raise ValueError("weekly_hours 须为 0–168 的数字或 null")
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="新建档案模板，拒绝覆盖")
    show = commands.add_parser("show", help="只读检查并显示档案")
    show.add_argument("--section", choices=tuple(key for key in PROFILE if key != "schema_version"))
    args = parser.parse_args()
    try:
        if args.command == "init":
            fd = os.open(args.profile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(PROFILE, target, ensure_ascii=False, indent=2)
                target.write("\n")
            print("已新建求职档案模板")
        else:
            data = validate(json.loads(args.profile.read_text(encoding="utf-8")))
            print(json.dumps(data[args.section] if args.section else data, ensure_ascii=False, indent=2))
    except FileExistsError:
        parser.exit(2, "档案文件已存在，原文件未覆盖。\n")
    except OSError:
        parser.exit(2, "无法访问指定档案。请检查父目录、路径和权限。\n")
    except (ValueError, TypeError) as error:
        parser.exit(2, f"档案无效。{error}\n")


if __name__ == "__main__":
    main()
