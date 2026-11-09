#!/usr/bin/env python3
"""Record and review confirmed application events in a user-selected local database."""

import argparse
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from check_jobs import CHINA, DATE_ONLY, parse_boundary, parse_datetime


APP_ID = 0x43415250
STAGES = ("tracking", "submitted", "assessment", "interview", "offer", "accepted")
TERMINAL = {"accepted", "rejected", "withdrawn"}
FIELDS = {
    "event_id", "job_id", "employer", "title", "stage", "at", "resume_version",
    "next_action", "due_at", "feedback",
}
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}\Z")


def validate(event, now):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError("记录字段须与本地投递记录说明一致")
    for key in ("event_id", "job_id"):
        if not isinstance(event[key], str) or not IDENTIFIER.fullmatch(event[key]):
            raise ValueError(f"{key} 须为稳定的短编号")
    for key in ("employer", "title", "resume_version", "next_action", "feedback"):
        value = event[key]
        if key in {"employer", "title"} or value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} 须为非空文本或允许的空值")
    if event["stage"] not in STAGES and event["stage"] not in TERMINAL:
        raise ValueError("无法识别投递阶段")
    at = parse_datetime(event["at"])
    if at > now:
        raise ValueError("投递事件时间不能晚于现在")
    if event["due_at"] is not None:
        if event["next_action"] is None:
            raise ValueError("填写截止时间时也须提供下一步动作")
        parse_boundary(event["due_at"])
    return {**event, "at": at.isoformat(timespec="microseconds")}


def writable_database(path):
    # New files are private on systems supporting POSIX permissions.
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    return sqlite3.connect(path)


def check_database(db, create=False):
    app_id = db.execute("PRAGMA application_id").fetchone()[0]
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if app_id == APP_ID and version == 1:
        return
    empty = not db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    if not create or app_id or version or not empty:
        raise ValueError("文件不是可读取的秋招投递记录数据库")
    db.execute("""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX events_by_job ON events (job_id, at)")
    db.execute(f"PRAGMA application_id = {APP_ID}")
    db.execute("PRAGMA user_version = 1")


def record(path, event, now):
    event = validate(event, now)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with closing(writable_database(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        check_database(db, create=True)
        existing = db.execute("SELECT payload FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
        if existing:
            if existing[0] != payload:
                raise ValueError("同一事件编号已有不同内容")
            return False
        latest = db.execute(
            "SELECT payload FROM events WHERE job_id = ? ORDER BY at DESC, rowid DESC LIMIT 1",
            (event["job_id"],),
        ).fetchone()
        if latest:
            previous = json.loads(latest[0])
            if event["at"] < previous["at"]:
                raise ValueError("追加的事件早于该岗位已有记录")
            if any(event[key] != previous[key] for key in ("employer", "title")):
                raise ValueError("同一岗位编号不能更换招聘方或岗位名称")
            before, after = previous["stage"], event["stage"]
            if before in TERMINAL and after != before:
                raise ValueError("已结束的投递不能直接回到其他阶段，请为新一轮使用新岗位编号")
            if before in STAGES and after in STAGES and STAGES.index(after) < STAGES.index(before):
                raise ValueError("投递阶段不可倒退")
        db.execute(
            "INSERT INTO events (event_id, job_id, at, payload) VALUES (?, ?, ?, ?)",
            (event["event_id"], event["job_id"], event["at"], payload),
        )
    return True


def review(path, now, start, job_id=None):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        check_database(db)
        select = "SELECT payload FROM events WHERE at <= ?"
        parameters = [now.isoformat(timespec="microseconds")]
        if job_id:
            select += " AND job_id = ?"
            parameters.append(job_id)
        history = [
            json.loads(item[0]) for item in db.execute(select + " ORDER BY at, rowid", parameters)
        ]
    jobs = {}
    period = {stage: set() for stage in (*STAGES, "rejected", "withdrawn")}
    feedback = []
    for event in history:
        key = event["job_id"]
        previous = jobs.get(key, {})
        stage = event["stage"]
        if date.fromisoformat(event["at"][:10]) >= start:
            if stage != previous.get("stage"):
                period[stage].add(key)
            if event["feedback"]:
                feedback.append({
                    "job_id": key, "stage": stage, "at": event["at"], "feedback": event["feedback"],
                })
        jobs[key] = {
            **event,
            "resume_version": event["resume_version"] or previous.get("resume_version"),
        }
    actions = []
    for event in jobs.values():
        if event["stage"] in TERMINAL or not event["next_action"]:
            continue
        due, _ = parse_boundary(event["due_at"])
        overdue = False
        if due:
            date_only = DATE_ONLY.fullmatch(event["due_at"])
            overdue = now.date() > due.date() if date_only else now >= due
        actions.append({**event, "overdue": overdue})
    last = datetime.max.replace(tzinfo=CHINA)
    actions.sort(key=lambda row: (parse_boundary(row["due_at"])[0] or last, row["job_id"]))
    return {
        "as_of": now.isoformat(), "since": start.isoformat(),
        "jobs_entering_each_stage": {key: len(value) for key, value in period.items()},
        "next_actions": actions, "latest_by_job": list(jobs.values()), "confirmed_feedback": feedback,
        **({"history": history} if job_id else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("record")
    add.add_argument("event", type=Path)
    read = commands.add_parser("review")
    read.add_argument("--since", type=date.fromisoformat, help="Review starting on this Beijing date")
    read.add_argument("--job", help="Include all recorded events for this job ID")
    args = parser.parse_args()
    now = datetime.now(CHINA)
    try:
        if args.command == "record":
            event = json.loads(args.event.read_text(encoding="utf-8"))
            result = {"recorded": record(args.database, event, now), "event_id": event["event_id"]}
        else:
            start = args.since or now.date() - timedelta(days=6)
            if start > now.date():
                raise ValueError("复盘起点不能在未来")
            result = review(args.database, now, start, job_id=args.job)
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        parser.exit(2, f"无法处理投递记录：{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
