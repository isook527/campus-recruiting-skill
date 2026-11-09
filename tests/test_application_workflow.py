import copy
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from test_check_jobs import NOW, ROOT, example

from application_log import record, review
from check_jobs import CHINA
from prepare_application import rank, render_packet


def application(job_id, state="met", complete=True):
    return {
        "job_id": job_id,
        "requirements_complete": complete,
        "criteria": [
            {
                "kind": "required", "requirement": "六级或同等外语能力",
                "source": "模拟公告：应聘资格",
                "state": state, "fact_ids": [] if state == "unknown" else ["F1"],
                "next_step": "核对同等资格的证明",
            },
            {
                "kind": "preferred", "requirement": "学生干部优先",
                "source": "模拟公告：优先条件",
                "state": "unknown", "fact_ids": [], "next_step": "按本人经历确认",
            },
        ],
        "resume_version": "cv-support-01",
        "resume": [{
            "section": "experience", "text": "记录班费收支并公示",
            "fact_ids": ["F2"], "rationale": "与台账维护任务相关",
        }],
        "questions": [
            {"text": question, "fact_ids": ["F2"]} for question in (
                "记录哪些项目？", "怎样确认公示内容？", "本人负责哪一步？",
            )
        ],
        "checklist": [{"item": "核对附件格式", "state": "todo"}],
    }


class ApplicationPacketTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "facts": {"F1": "提供了等效语言证明", "F2": "担任生活委员，记录班费及公示"},
            "jobs": [example()],
            "reviews": [application("demo-001")],
        }

    def test_orders_ready_before_unknown_and_closed(self):
        self.data["jobs"].extend([
            example(id="closed", city="杭州", deadline="2030-11-08"),
            example(id="unknown", city="上海", deadline="2030-11-10"),
            example(id="earlier", city="深圳", deadline="2030-11-11"),
            example(id="campaign", scope="campaign", status="campaign_open"),
        ])
        self.data["reviews"].extend([
            application("closed"), application("unknown", state="unknown"),
            application("earlier"), application("campaign"),
        ])
        result = rank(self.data, NOW)
        self.assertEqual(
            [(item["id"], item["decision"]) for item in result],
            [("earlier", "ready"), ("demo-001", "ready"), ("unknown", "verify"),
             ("campaign", "verify"), ("closed", "skip")],
        )

    def test_requires_complete_hard_conditions_and_current_evidence(self):
        self.data["reviews"][0]["requirements_complete"] = False
        self.assertEqual(rank(self.data, NOW)[0]["decision"], "verify")
        self.data["reviews"][0]["requirements_complete"] = True
        self.assertEqual(rank(self.data, NOW + timedelta(days=1))[0]["decision"], "verify")
        self.data["reviews"][0]["criteria"][0]["state"] = "gap"
        self.assertEqual(rank(self.data, NOW)[0]["decision"], "skip")

    def test_missing_fact_cannot_be_used_to_reject_a_candidate(self):
        criterion = self.data["reviews"][0]["criteria"][0]
        criterion.update(state="gap", fact_ids=[])
        with self.assertRaisesRegex(ValueError, "未提供资料"):
            rank(self.data, NOW)

    def test_renders_editable_resume_with_evidence_and_marks_pending(self):
        self.data["reviews"][0] = application("demo-001", state="unknown")
        packet = render_packet(self.data, rank(self.data, NOW), "demo-001", replay=True)
        resume, reasons = packet.split("## 可编辑简历", 1)[1].split("## 改写依据", 1)
        self.assertIn("记录班费收支并公示", resume)
        self.assertNotIn("F2", resume)
        self.assertIn("F2 担任生活委员", reasons)
        self.assertIn("准备草稿", packet)
        self.assertIn("历史回放", packet)
        self.assertIn("cv-support-01", packet)
        self.assertEqual(packet.count("（F2）"), 3)

    def test_refuses_unconfirmed_resume_facts_or_unrelated_questions(self):
        ranked = rank(self.data, NOW)
        invalid = copy.deepcopy(self.data)
        invalid["reviews"][0]["resume"][0]["fact_ids"] = ["made-up-fact"]
        with self.assertRaisesRegex(ValueError, "已确认"):
            render_packet(invalid, ranked, "demo-001")
        invalid = copy.deepcopy(self.data)
        invalid["reviews"][0]["questions"][0]["fact_ids"] = ["F1"]
        with self.assertRaisesRegex(ValueError, "本版简历"):
            render_packet(invalid, ranked, "demo-001")


def event(event_id, stage, at, **updates):
    return {
        "event_id": event_id, "job_id": "synthetic-001", "employer": "虚构单位",
        "title": "综合支持", "stage": stage, "at": at, "resume_version": None,
        "next_action": None, "due_at": None, "feedback": None, **updates,
    }


class LocalLogTest(unittest.TestCase):
    def test_reopens_in_new_process_and_idempotent_concurrent_records(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db = base / "记录.sqlite3"
            record_path = base / "确认事件.json"
            now = datetime.now(CHINA)
            record_path.write_text(json.dumps(event(
                "first", "interview", (now - timedelta(seconds=5)).isoformat(),
                resume_version="cv-support-02", next_action="带上证件",
                due_at=(now + timedelta(days=1)).date().isoformat(),
            )), encoding="utf-8")
            cli = [sys.executable, str(ROOT / "scripts/application_log.py"), str(db)]

            def run(*args):
                result = subprocess.run([*cli, *args], check=True, capture_output=True, text=True)
                return json.loads(result.stdout)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run, "record", str(record_path)) for _ in range(2)]
                self.assertEqual(sorted(item.result()["recorded"] for item in futures), [False, True])
            saved = run("review", "--job", "synthetic-001")
            self.assertEqual(len(saved["history"]), 1)
            self.assertEqual(saved["next_actions"][0]["next_action"], "带上证件")
            self.assertEqual(saved["latest_by_job"][0]["resume_version"], "cv-support-02")
            self.assertEqual(saved["confirmed_feedback"], [])

    def test_period_counts_distinct_stage_entries_and_reports_only_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite3"
            record(db, event("sent", "submitted", "2030-11-02T10:00:00+08:00",
                             resume_version="cv-01"), NOW)
            record(db, event("interview-1", "interview", "2030-11-04T10:00:00+08:00",
                             feedback="招聘方建议准备一个核对实例"), NOW)
            record(db, event("interview-2", "interview", "2030-11-07T10:00:00+08:00",
                             next_action="准备复试", due_at="2030-11-09"), NOW)
            report = review(db, NOW, date(2030, 11, 3))
            self.assertEqual(report["jobs_entering_each_stage"]["submitted"], 0)
            self.assertEqual(report["jobs_entering_each_stage"]["interview"], 1)
            self.assertEqual(report["latest_by_job"][0]["resume_version"], "cv-01")
            self.assertEqual(len(report["confirmed_feedback"]), 1)
            self.assertFalse(report["next_actions"][0]["overdue"])
            tomorrow = review(db, NOW + timedelta(days=1), date(2030, 11, 3))
            self.assertTrue(tomorrow["next_actions"][0]["overdue"])

    def test_invalid_transition_preserves_recorded_history(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite3"
            record(db, event("declined", "rejected", "2030-11-08T10:00:00+08:00"), NOW)
            with self.assertRaisesRegex(ValueError, "已结束"):
                record(db, event("new", "interview", "2030-11-09T12:00:00+08:00"), NOW)
            report = review(db, NOW, date(2030, 11, 3), job_id="synthetic-001")
            self.assertEqual([item["event_id"] for item in report["history"]], ["declined"])


if __name__ == "__main__":
    unittest.main()
