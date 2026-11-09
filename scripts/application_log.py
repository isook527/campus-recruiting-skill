#!/usr/bin/env python3
"""Record, review, migrate, and export private local application events."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from application_funnel import diagnose
from check_jobs import CHINA, DATE_ONLY, parse_boundary, parse_datetime


APP_ID = 0x43415250
CURRENT_VERSION = 2
LEGACY_VERSION = 1
STAGES = ("tracking", "submitted", "assessment", "interview", "offer", "accepted")
TERMINAL = {"accepted", "rejected", "withdrawn"}
FIELDS = {
    "event_id", "job_id", "employer", "title", "stage", "at", "resume_version",
    "next_action", "due_at", "feedback",
}
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}\Z")
MOBILE = re.compile(r"(?<!\d)(?:(?:\+|00)86[\s-]*)?1[3-9](?:[\s-]?\d){9}(?!\d)")
CHINESE_ID = re.compile(
    r"(?<!\d)(?:[1-9](?:[ -]?\d){16}[ -]?[0-9Xx]|[1-9](?:[ -]?\d){14})(?![0-9Xx])"
)
REDACTED = "[已移除敏感信息]"
NORMALIZE_SENSITIVE = str.maketrans({
    **{chr(ord("０") + number): str(number) for number in range(10)},
    "Ｘ": "X", "ｘ": "x", "＋": "+", "－": "-", "‐": "-", "‑": "-",
    "–": "-", "—": "-", "　": " ",
})


def _sensitive_spans(text):
    normalized = text.translate(NORMALIZE_SENSITIVE)
    spans = [match.span() for match in MOBILE.finditer(normalized)]
    # Deliberately block malformed-but-ID-like values too: a mistyped ID is still private.
    spans.extend(match.span() for match in CHINESE_ID.finditer(normalized))
    if not spans:
        return []
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def redact_sensitive(text):
    if not isinstance(text, str):
        return text
    spans = _sensitive_spans(text)
    if not spans:
        return text
    parts = []
    cursor = 0
    for start, end in spans:
        parts.extend((text[cursor:start], REDACTED))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _contains_sensitive(value):
    if isinstance(value, str):
        return bool(_sensitive_spans(value))
    if isinstance(value, dict):
        return any(_contains_sensitive(key) or _contains_sensitive(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive(item) for item in value)
    return False


def assert_no_sensitive(value):
    if _contains_sensitive(value):
        raise ValueError("记录包含疑似中国居民身份证号或手机号，请删除敏感信息后再记录")


def _safe_identifier(value):
    if not isinstance(value, str) or not _sensitive_spans(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"redacted-{digest}"


def sanitize_legacy_event(event):
    if not isinstance(event, dict):
        raise ValueError("历史投递记录格式无效，无法安全读取")
    safe = {}
    for key, value in event.items():
        safe_key = redact_sensitive(key)
        if key in {"event_id", "job_id"}:
            safe[safe_key] = _safe_identifier(value)
        elif isinstance(value, str):
            safe[safe_key] = redact_sensitive(value)
        else:
            safe[safe_key] = value
    assert_no_sensitive(safe)
    return safe


def validate(event, now):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError("记录字段须与本地投递记录说明一致")
    assert_no_sensitive(event)
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


def _configure(db):
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def _readonly_database(path):
    return _configure(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))


def _writable_existing_database(path):
    return _configure(sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True))


def writable_database(path):
    # New files are private on systems supporting POSIX permissions.
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    return _configure(sqlite3.connect(path))


def _create_schema_v2(db):
    db.execute("""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, at TEXT NOT NULL,
            payload TEXT NOT NULL,
            privacy_checked INTEGER NOT NULL CHECK (privacy_checked IN (0, 1))
        )
    """)
    db.execute("CREATE INDEX events_by_job ON events (job_id, at)")
    db.execute(f"PRAGMA application_id = {APP_ID}")
    db.execute(f"PRAGMA user_version = {CURRENT_VERSION}")


def check_database(db, create=False):
    app_id = db.execute("PRAGMA application_id").fetchone()[0]
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if app_id == APP_ID and version in {LEGACY_VERSION, CURRENT_VERSION}:
        return version
    empty = not db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    if not create or app_id or version or not empty:
        raise ValueError("文件不是可读取的秋招投递记录数据库")
    _create_schema_v2(db)
    return CURRENT_VERSION


def _decode_payload(payload):
    try:
        event = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("历史投递记录格式无效，无法安全读取") from error
    safe = sanitize_legacy_event(event)
    if set(safe) != FIELDS:
        raise ValueError("历史投递记录字段不完整，无法安全读取")
    return safe


def record(path, event, now):
    event = validate(event, now)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with closing(writable_database(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        version = check_database(db, create=True)
        if version == LEGACY_VERSION:
            raise ValueError("旧版数据库当前只读；请先使用 migrate 命令创建备份并升级")
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
            previous = _decode_payload(latest[0])
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
            "INSERT INTO events (event_id, job_id, at, payload, privacy_checked) VALUES (?, ?, ?, ?, 1)",
            (event["event_id"], event["job_id"], event["at"], payload),
        )
    return True


def _read_history(db, now=None, job_id=None):
    version = check_database(db)
    select = "SELECT payload FROM events"
    conditions = []
    parameters = []
    if now is not None:
        conditions.append("at <= ?")
        parameters.append(now.isoformat(timespec="microseconds"))
    if job_id:
        conditions.append("job_id = ?")
        parameters.append(job_id)
    if conditions:
        select += " WHERE " + " AND ".join(conditions)
    history = [_decode_payload(item[0]) for item in db.execute(select + " ORDER BY at, rowid", parameters)]
    return version, history


def review(path, now, start, job_id=None):
    with closing(_readonly_database(path)) as db:
        db.execute("BEGIN")
        _, history = _read_history(db, now=now, job_id=job_id)
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


def funnel(path, now, start, job_ids=None):
    with closing(_readonly_database(path)) as db:
        db.execute("BEGIN")
        _, history = _read_history(db, now=now)
    if job_ids:
        selected = {_safe_identifier(job_id) for job_id in job_ids}
        history = [event for event in history if event["job_id"] in selected]
    return diagnose(history, now, start)


def _paths_are_same(source, destination):
    try:
        return source.resolve(strict=True) == destination.resolve(strict=False)
    except OSError:
        return False


def _reserve_destination(destination):
    try:
        return os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("目标文件已存在；为防止覆盖，请选择新的路径") from error


def backup_database(path, destination):
    if _paths_are_same(path, destination):
        raise ValueError("备份目标不能与原数据库相同")
    fd = _reserve_destination(destination)
    os.close(fd)
    completed = False
    try:
        with closing(_readonly_database(path)) as source, closing(_configure(sqlite3.connect(destination))) as target:
            version = check_database(source)
            source.backup(target)
            check_database(target)
        completed = True
        return version
    finally:
        if not completed:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass


def _migrate_v1_to_v2(db):
    # Schema-only migration: old rows remain tagged 0 and are redacted at every read/export.
    # This avoids rewriting historical user data during an operational upgrade.
    db.execute(
        "ALTER TABLE events ADD COLUMN privacy_checked INTEGER NOT NULL DEFAULT 0 "
        "CHECK (privacy_checked IN (0, 1))"
    )
    db.execute(f"PRAGMA user_version = {CURRENT_VERSION}")


def migrate_database(path, backup_path):
    # mode=rw makes a missing source fail without leaving an empty placeholder behind.
    with closing(_writable_existing_database(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            # Re-check only after obtaining the writer lock so concurrent migrations serialize.
            version = check_database(db)
            if version == CURRENT_VERSION:
                db.rollback()
                return False, version
            # This lock prevents a legacy writer changing the source between the exact
            # SQLite backup and the schema transaction. Readers can keep their snapshot.
            backup_database(path, backup_path)
            _migrate_v1_to_v2(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return True, version


def _exclusive_json_write(destination, value):
    fd = _reserve_destination(destination)
    completed = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        completed = True
    finally:
        if not completed:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass


def export_database(path, destination, now):
    if _paths_are_same(path, destination):
        raise ValueError("导出目标不能与原数据库相同")
    with closing(_readonly_database(path)) as db:
        db.execute("BEGIN")
        version, events = _read_history(db)
    document = {
        "format": "campus-application-events",
        "source_schema_version": version,
        "exported_at": now.isoformat(),
        "events": events,
    }
    assert_no_sensitive(document)
    _exclusive_json_write(destination, document)
    return version, len(events)


def _safe_error(error):
    return redact_sensitive(str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("record", help="从 JSON 文件记录一个已确认的投递事件")
    add.add_argument("event", metavar="EVENT_JSON_PATH", type=Path, help="事件 JSON 文件路径，例如 event.json")
    read = commands.add_parser("review", help="读取安全的投递复盘")
    read.add_argument("--since", type=date.fromisoformat, help="Review starting on this Beijing date")
    read.add_argument("--job", help="Include all recorded events for this job ID")
    funnel_command = commands.add_parser("funnel", help="按实际提交批次复盘各关转化与待反馈")
    funnel_command.add_argument("--since", type=date.fromisoformat, help="提交队列起点（北京时间）")
    funnel_command.add_argument("--job", action="append", help="只看指定岗位编号，可重复传入")
    migrate = commands.add_parser("migrate", help="备份后把 v1 数据库事务升级到 v2")
    migrate.add_argument("backup", metavar="BACKUP_SQLITE_PATH", type=Path)
    export = commands.add_parser("export", help="导出不含身份证号和手机号的 JSON 快照")
    export.add_argument("destination", metavar="EXPORT_JSON_PATH", type=Path)
    backup = commands.add_parser("backup", help="使用 SQLite 在线备份创建不覆盖的精确副本")
    backup.add_argument("destination", metavar="BACKUP_SQLITE_PATH", type=Path)
    args = parser.parse_args()
    now = datetime.now(CHINA)
    try:
        if args.command == "record":
            try:
                event_text = args.event.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError(
                    "record 需要一个可读取的事件 JSON 文件路径。"
                    "请先把事件写到 event.json，再把文件路径传给 record。"
                ) from error
            event = json.loads(event_text)
            result = {"recorded": record(args.database, event, now), "event_id": event["event_id"]}
        elif args.command == "review":
            start = args.since or now.date() - timedelta(days=6)
            if start > now.date():
                raise ValueError("复盘起点不能在未来")
            result = review(args.database, now, start, job_id=args.job)
        elif args.command == "funnel":
            start = args.since or now.date() - timedelta(days=27)
            if start > now.date():
                raise ValueError("漏斗起点不能在未来")
            result = funnel(args.database, now, start, job_ids=args.job)
        elif args.command == "migrate":
            changed, previous = migrate_database(args.database, args.backup)
            result = {
                "migrated": changed, "from_version": previous,
                "to_version": CURRENT_VERSION, "backup_created": changed,
            }
        elif args.command == "export":
            version, count = export_database(args.database, args.destination, now)
            result = {"exported": True, "events": count, "source_schema_version": version}
        else:
            version = backup_database(args.database, args.destination)
            result = {"backed_up": True, "source_schema_version": version}
    except (KeyError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        parser.exit(2, f"无法处理投递记录：{_safe_error(error)}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
