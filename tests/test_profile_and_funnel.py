import copy
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from test_check_jobs import ROOT
from application_funnel import diagnose
from application_log import funnel, record
from candidate_profile import PROFILE, validate
from check_jobs import CHINA


NOW = datetime(2030, 11, 9, 16, tzinfo=CHINA)
START = date(2030, 10, 13)


def history(job, stages, start=NOW - timedelta(days=15)):
    return [
        {
            "event_id": f"{job}-{index}", "job_id": job,
            "employer": "合成单位", "title": "综合支持", "stage": stage,
            "at": (start + timedelta(hours=index)).isoformat(),
            "resume_version": None, "next_action": None, "due_at": None, "feedback": None,
        }
        for index, stage in enumerate(stages)
    ]


class ProfileTest(unittest.TestCase):
    def test_accepts_partial_profile_with_education_and_fact_ids(self):
        profile = copy.deepcopy(PROFILE)
        profile["education"].update(first_degree="本科", graduation_month="2030-06", gpa="3.6/4.0")
        profile["preferences"].update(cities=["北京"], weekly_hours=7.5)
        profile.update(experience_ids=["F1", "F2"], fact_cards_file="facts.local.json")
        self.assertEqual(validate(profile), profile)
        for unsafe in ("../facts.md", "/facts.md", "C:\\facts.md"):
            profile["fact_cards_file"] = unsafe
            with self.assertRaisesRegex(ValueError, "相对文件路径"):
                validate(profile)

    def test_init_is_private_and_show_is_selective_and_checks_privacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile.local.json"
            command = [sys.executable, str(ROOT / "scripts/candidate_profile.py"), str(profile)]
            subprocess.run([*command, "init"], check=True, capture_output=True)
            self.assertEqual(stat.S_IMODE(profile.stat().st_mode), 0o600)
            initial = json.loads(profile.read_text())
            initial["preferences"]["cities"] = ["上海"]
            profile.write_text(json.dumps(initial))
            duplicate = subprocess.run([*command, "init"], capture_output=True)
            self.assertEqual(duplicate.returncode, 2)
            preferences = subprocess.run([*command, "show", "--section", "preferences"],
                                         check=True, text=True, capture_output=True)
            self.assertEqual(json.loads(preferences.stdout)["cities"], ["上海"])
            self.assertNotIn("education", preferences.stdout)
            fake_phone = "199" + "0000" + "0000"
            initial["qualifications"]["english"] = fake_phone
            profile.write_text(json.dumps(initial))
            blocked = subprocess.run([*command, "show"], text=True, capture_output=True)
            self.assertEqual(blocked.returncode, 2)
            self.assertNotIn(fake_phone, blocked.stdout + blocked.stderr)


class FunnelTest(unittest.TestCase):
    def test_no_reply_is_pending_and_never_zero_conversion(self):
        events = [entry for i in range(32) for entry in history(f"job-{i}", ["submitted"])]
        result = diagnose(events, NOW, START)
        first = result["gates"]["submitted"]
        self.assertEqual((first["entered"], first["pending_seven_days"]), (32, 32))
        self.assertEqual(first["rejected"], 0)
        self.assertIsNone(first["conversion"])
        self.assertIsNone(result["weakest_observed_gate"])
        self.assertIn("提交", result["next_week_action"])

    def test_funnel_skips_unobserved_steps_and_excludes_withdrawals_and_missing_submissions(self):
        events = [
            *history("a", ["submitted", "assessment", "rejected"]),
            *history("b", ["submitted", "assessment", "rejected", "rejected"]),
            *history("c", ["submitted", "assessment", "interview", "offer"]),
            *history("d", ["submitted", "assessment", "withdrawn"]),
            *history("e", ["submitted", "interview", "interview", "offer"]),
            *history("f", ["assessment", "rejected"]),
            *history("old", ["submitted", "rejected"], NOW - timedelta(days=40)),
        ]
        result = diagnose(events, NOW, START)
        first, assessment, interview = (result["gates"][step] for step in ("submitted", "assessment", "interview"))
        self.assertEqual(first["passed"], 5)
        self.assertEqual((assessment["passed"], assessment["rejected"], assessment["withdrawn"]), (1, 2, 1))
        self.assertAlmostEqual(assessment["conversion"], 1 / 3)
        self.assertEqual(interview["entered"], 2)
        self.assertEqual(result["weakest_observed_gate"], "assessment")
        self.assertEqual(result["jobs_missing_submission_event"], 1)

    def test_reads_real_log_without_write_and_can_select_one_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "log.sqlite3"
            for item in history("a", ["submitted", "assessment"]) + history("b", ["submitted", "rejected"]):
                record(database, item, NOW)
            before = database.read_bytes()
            report = funnel(database, NOW, START, job_ids=["a"])
            self.assertEqual(report["cohort_size"], 1)
            self.assertEqual(report["gates"]["submitted"]["conversion"], 1)
            self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
