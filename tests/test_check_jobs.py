from datetime import date
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_jobs import audit, parse_datetime  # noqa: E402
from check_sources import source_status  # noqa: E402


NOW = parse_datetime("2030-11-09T16:00:00+08:00")


def example(**changes):
    return {
        "id": "demo-001",
        "employer": "模拟招聘方",
        "title": "项目支持",
        "batch": "2031届秋招",
        "scope": "position",
        "employment_type": "campus",
        "city": "北京",
        "eligibility": "2031届",
        "salary": None,
        "announcement_url": "https://example.org/campus",
        "application_url": "https://example.org/roles/001",
        "checked_at": "2030-11-09T15:30:00+08:00",
        "opens_at": None,
        "deadline": None,
        "status": "verified_open",
        "announcement_evidence": "模拟公告",
        "application_evidence": "模拟网申状态",
        **changes,
    }


class CheckJobsTest(unittest.TestCase):
    def reason(self, **changes):
        return audit([example(**changes)], NOW)["excluded"][0]["reason"]

    def test_keeps_position_and_campaign_separate(self):
        campaign = example(id="demo-002", scope="campaign", status="campaign_open")
        eligible = audit([example(), campaign], NOW)["eligible_by_record"]
        self.assertEqual([row["scope"] for row in eligible], ["position", "campaign"])

    def test_does_not_upgrade_unverified_record(self):
        self.assertEqual(self.reason(status="unverified"), "unverified")

    def test_excludes_past_and_uncertain_same_day_deadlines(self):
        self.assertEqual(self.reason(deadline="2030-11-08"), "closed")
        self.assertEqual(self.reason(deadline="2030-11-09"), "deadline_time_unconfirmed")
        self.assertEqual(self.reason(deadline="2030-11-09T08:00:00Z"), "closed")

    def test_rejects_future_and_old_observations(self):
        with self.assertRaisesRegex(ValueError, "future"):
            audit([example(checked_at="2030-11-09T16:00:01+08:00")], NOW)
        self.assertEqual(self.reason(checked_at="2030-11-09T07:59:00+08:00"), "stale")
        valid = audit([example(checked_at="2030-11-09T08:30:00+08:00")], NOW)
        self.assertEqual(valid["verification_window_ends_at"]["demo-001"], "2030-11-09T16:30:00+08:00")

    def test_distinguishes_not_started_from_stale_observation(self):
        self.assertEqual(self.reason(opens_at="2030-11-10"), "not_started")
        self.assertEqual(self.reason(opens_at="2030-11-09T15:45:00+08:00"), "stale")

    def test_requires_both_evidence_fields_and_public_url(self):
        with self.assertRaisesRegex(ValueError, "application_evidence"):
            audit([example(application_evidence=None)], NOW)
        with self.assertRaisesRegex(ValueError, "tracking"):
            audit([example(application_url="https://example.org/apply?token=sample")], NOW)

    def test_schema_error_identifies_record_and_fields(self):
        broken = example(id="second", job_type="campus")
        del broken["city"]
        with self.assertRaisesRegex(ValueError, r"record 2 .*second.*missing fields city.*unexpected fields job_type"):
            audit([example(), broken], NOW)

    def test_invalid_status_lists_accepted_values(self):
        with self.assertRaisesRegex(ValueError, r"record 1 .*invalid status.*closed.*unverified.*verified_open"):
            audit([example(status="open")], NOW)

    def test_duplicate_and_conflicting_status_do_not_leak_into_open_list(self):
        result = audit([example(), example(id="demo-002", status="closed")], NOW)
        self.assertEqual(result["eligible_by_record"], [])
        self.assertEqual(
            {row["reason"] for row in result["excluded"]},
            {"duplicate_requires_resolution"},
        )
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            audit([example(), example()], NOW)

    def test_same_title_in_distinct_cities_is_preserved(self):
        result = audit([example(), example(id="demo-002", city="上海")], NOW)
        self.assertEqual(len(result["eligible_by_record"]), 2)

    def test_explicit_source_type_and_official_conflict_are_fail_closed(self):
        self.assertEqual(self.reason(source_type="third_party"), "source_not_confirmed")
        self.assertEqual(self.reason(source_type="unknown"), "source_not_confirmed")
        self.assertEqual(self.reason(source_type="employer", official_conflict=True), "official_conflict")
        with self.assertRaisesRegex(ValueError, "invalid source_type"):
            audit([example(source_type="official")], NOW)

    def test_deadline_countdown_preserves_precision(self):
        for deadline, expected in [
            (None, {"precision": "unknown"}),
            ("2030-11-10", {"precision": "date", "calendar_days": 1}),
            ("2030-11-10T12:00:00+08:00", {"precision": "time", "seconds": 72000}),
        ]:
            with self.subTest(deadline=deadline):
                self.assertEqual(audit([example(deadline=deadline)], NOW)["deadline_countdown"]["demo-001"], expected)

    def test_cli_warning_exit_and_validation_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "jobs.json"
            cli = [sys.executable, str(ROOT / "scripts/check_jobs.py"), str(data),
                   "--as-of", NOW.isoformat(), "--warn-exit"]
            data.write_text(json.dumps([example(checked_at="2030-11-09T07:59:00+08:00")]))
            warned = subprocess.run(cli, capture_output=True, text=True)
            self.assertEqual(warned.returncode, 1)
            self.assertEqual(json.loads(warned.stdout)["warnings"][0]["reason"], "stale")
            data.write_text(json.dumps([example(status="invented")]))
            invalid = subprocess.run(cli, capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("invalid status", invalid.stderr)

    def test_source_navigation_expiry_is_independent_of_job_freshness(self):
        sources = "\n".join([
            "| [刚核验](https://example.org/) | 导航 | 2030-10-10 |",
            "| [旧入口](https://example.org/) | 导航 | 2030-10-09 |",
            "| [未知](https://example.org/) | 导航 | — |",
        ])
        self.assertEqual(
            [status for _, status, _ in source_status(sources, date(2030, 11, 9))],
            ["导航日期有效", "需重新核对", "需重新核对"],
        )

    def test_cli_uses_default_schema_and_timezone(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "jobs.json"
            data.write_text(json.dumps([example()]), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts/check_jobs.py"), str(data)]
            result = subprocess.run(
                [*command, "--as-of", "2030-11-09T08:00:00Z"],
                check=True, capture_output=True, text=True,
            )
        output = json.loads(result.stdout)
        self.assertEqual(output["as_of"], "2030-11-09T16:00:00+08:00")
        self.assertEqual(output["eligible_by_record"][0]["id"], "demo-001")


if __name__ == "__main__":
    unittest.main()
