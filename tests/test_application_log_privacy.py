import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from application_log import (  # noqa: E402
    APP_ID,
    CURRENT_VERSION,
    REDACTED,
    backup_database,
    export_database,
    migrate_database,
    record,
    review,
)
from check_jobs import CHINA  # noqa: E402


NOW = datetime(2030, 11, 9, 16, 0, tzinfo=CHINA)
MOBILE = "+86 138-0013-8000"
CHINESE_ID = "11010519491231002X"
MALFORMED_ID = "ID=11010519991340123X"
FULLWIDTH_PRIVATE = "card-１１０１０５１９９９１３４０１２３Ｘ"
FULLWIDTH_MOBILE = "＋８６ １３８－００１３－８０００"
SEPARATED_ID = "ID=110105-19491231 002X"


def event(event_id="event-001", **updates):
    return {
        "event_id": event_id,
        "job_id": "synthetic-001",
        "employer": "虚构单位",
        "title": "综合支持",
        "stage": "interview",
        "at": "2030-11-09T10:00:00+08:00",
        "resume_version": "cv-01",
        "next_action": "准备复试",
        "due_at": "2030-11-10",
        "feedback": None,
        **updates,
    }


def create_v1(path, payload):
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                at TEXT NOT NULL, payload TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX events_by_job ON events (job_id, at)")
        db.execute(f"PRAGMA application_id = {APP_ID}")
        db.execute("PRAGMA user_version = 1")
        db.execute(
            "INSERT INTO events (event_id, job_id, at, payload) VALUES (?, ?, ?, ?)",
            (
                payload.get("event_id", "legacy-event"),
                payload.get("job_id", "legacy-job"),
                payload.get("at", "2030-11-09T10:00:00+08:00"),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )


def database_version(path):
    with sqlite3.connect(path) as db:
        return db.execute("PRAGMA user_version").fetchone()[0]


class ApplicationLogPrivacyTest(unittest.TestCase):
    def cli(self, database, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/application_log.py"), str(database), *map(str, args)],
            capture_output=True,
            text=True,
        )

    def test_record_blocks_mobile_and_chinese_id_without_echo_or_database_write(self):
        for number in (
            MOBILE, CHINESE_ID, MALFORMED_ID, FULLWIDTH_PRIVATE, FULLWIDTH_MOBILE, SEPARATED_ID,
        ):
            with self.subTest(private_value=number[:8]):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    database = base / "applications.sqlite3"
                    payload_path = base / "event.json"
                    payload_path.write_text(
                        json.dumps(event(feedback=f"请核对 {number}"), ensure_ascii=False),
                        encoding="utf-8",
                    )
                    result = self.cli(database, "record", payload_path)
                    combined = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("疑似中国居民身份证号或手机号", combined)
                    self.assertNotIn(number, combined)
                    self.assertFalse(database.exists())

    def test_legacy_review_redacts_historical_pii_without_implicit_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            create_v1(database, event(next_action=f"联系 {MOBILE}", feedback=f"证件 {CHINESE_ID}"))
            report = review(database, NOW, date(2030, 11, 3), job_id="synthetic-001")
            rendered = json.dumps(report, ensure_ascii=False)
            self.assertIn(REDACTED, rendered)
            self.assertNotIn(MOBILE, rendered)
            self.assertNotIn(CHINESE_ID, rendered)
            self.assertEqual(database_version(database), 1)

    def test_cli_migration_makes_exact_backup_and_keeps_legacy_rows_privacy_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "legacy.sqlite3"
            backup = base / "before-v2.sqlite3"
            create_v1(database, event(next_action=f"联系 {MOBILE}", feedback=f"证件 {CHINESE_ID}"))

            result = self.cli(database, "migrate", backup)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["migrated"])
            self.assertEqual(database_version(database), CURRENT_VERSION)
            self.assertEqual(database_version(backup), 1)
            self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)

            with sqlite3.connect(database) as db:
                stored = db.execute("SELECT payload FROM events").fetchone()[0]
                columns = [item[1] for item in db.execute("PRAGMA table_info(events)")]
                privacy_checked = db.execute("SELECT privacy_checked FROM events").fetchone()[0]
            self.assertIn("privacy_checked", columns)
            self.assertEqual(privacy_checked, 0)
            self.assertIn(MOBILE, stored)
            self.assertIn(CHINESE_ID, stored)

            rendered = json.dumps(
                review(database, NOW, date(2030, 11, 3), job_id="synthetic-001"),
                ensure_ascii=False,
            )
            self.assertNotIn(MOBILE, rendered)
            self.assertNotIn(CHINESE_ID, rendered)
            self.assertIn(REDACTED, rendered)

            with sqlite3.connect(backup) as db:
                original = db.execute("SELECT payload FROM events").fetchone()[0]
            self.assertIn(MOBILE, original)
            self.assertIn(CHINESE_ID, original)

    def test_failed_migration_rolls_back_schema_and_never_overwrites_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "legacy.sqlite3"
            existing_backup = base / "existing.sqlite3"
            create_v1(database, event())
            existing_backup.write_text("sentinel", encoding="utf-8")

            blocked = self.cli(database, "migrate", existing_backup)
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(existing_backup.read_text(encoding="utf-8"), "sentinel")
            self.assertEqual(database_version(database), 1)

            invalid_database = base / "invalid-legacy.sqlite3"
            migration_backup = base / "invalid-before-v2.sqlite3"
            create_v1(invalid_database, event())
            with sqlite3.connect(invalid_database) as db:
                db.execute("ALTER TABLE events ADD COLUMN privacy_checked INTEGER DEFAULT 0")
            failed = self.cli(invalid_database, "migrate", migration_backup)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(database_version(invalid_database), 1)
            self.assertEqual(database_version(migration_backup), 1)
            with sqlite3.connect(invalid_database) as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"events"})

            missing = base / "missing.sqlite3"
            missing_backup = base / "missing-backup.sqlite3"
            absent = self.cli(missing, "migrate", missing_backup)
            self.assertEqual(absent.returncode, 2)
            self.assertFalse(missing.exists())
            self.assertFalse(missing_backup.exists())

    def test_export_and_backup_use_committed_snapshot_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "applications.sqlite3"
            export_path = base / "events.json"
            backup_path = base / "snapshot.sqlite3"
            record(database, event(), NOW)

            with sqlite3.connect(database, timeout=5) as writer:
                writer.execute("BEGIN IMMEDIATE")
                uncommitted = event("event-002", at="2030-11-09T11:00:00+08:00")
                writer.execute(
                    "INSERT INTO events (event_id, job_id, at, payload, privacy_checked) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (
                        uncommitted["event_id"], uncommitted["job_id"], uncommitted["at"],
                        json.dumps(uncommitted, ensure_ascii=False, sort_keys=True),
                    ),
                )
                version, count = export_database(database, export_path, NOW)
                backup_version = backup_database(database, backup_path)
                writer.rollback()

            self.assertEqual((version, backup_version, count), (2, 2, 1))
            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual([item["event_id"] for item in exported["events"]], ["event-001"])
            with sqlite3.connect(backup_path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(os.stat(export_path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(backup_path).st_mode & 0o777, 0o600)

            export_path.write_text("sentinel", encoding="utf-8")
            blocked = self.cli(database, "export", export_path)
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(export_path.read_text(encoding="utf-8"), "sentinel")

    def test_concurrent_migrations_recheck_version_after_writer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "legacy.sqlite3"
            backups = [base / "first.sqlite3", base / "second.sqlite3"]
            create_v1(database, event())

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(migrate_database, database, path) for path in backups]
                results = [future.result() for future in futures]

            self.assertEqual(sorted(changed for changed, _ in results), [False, True])
            self.assertEqual(database_version(database), CURRENT_VERSION)
            self.assertEqual(sum(path.exists() for path in backups), 1)


if __name__ == "__main__":
    unittest.main()
