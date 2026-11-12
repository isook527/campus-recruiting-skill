import unittest
from datetime import timedelta

from test_application_workflow import application
from test_check_jobs import NOW, example
from prepare_application import deadline_notice, rank, render_packet


class DeadlineVisibilityTest(unittest.TestCase):
    def notice(self, deadline, status="verified_open", outcome="ready", **review):
        return deadline_notice(example(deadline=deadline), review, status, outcome, NOW)

    def test_converts_timezones_and_keeps_exact_remaining_time(self):
        result = self.notice("2030-11-10T01:00:00Z")
        self.assertEqual(result["at"], "2030-11-10 09:00（北京时间）")
        self.assertEqual(result["remaining"], "还剩 17 小时")
        self.assertEqual(result["label"], "24 小时内截止")
        self.assertEqual(self.notice("2030-11-10T22:00:00+08:00")["label"], "明天截止")

    def test_today_and_subminute_deadlines_remain_visible(self):
        self.assertEqual(self.notice((NOW + timedelta(hours=1)).isoformat())["label"], "今天截止")
        result = self.notice((NOW + timedelta(seconds=30)).isoformat())
        self.assertEqual(result["remaining"], "不足 1 分钟")
        self.assertEqual(self.notice(NOW.isoformat(), status="closed", outcome="skip")["label"], "已截止")

    def test_date_only_does_not_invent_an_exact_time_or_hour_count(self):
        today = self.notice("2030-11-09", status="deadline_time_unconfirmed", outcome="verify")
        self.assertEqual(today["label"], "今天截止 · 时刻待核")
        tomorrow = self.notice("2030-11-10")
        self.assertIn("具体时刻待核", tomorrow["at"])
        self.assertIn("1 个日历日", tomorrow["remaining"])
        self.assertNotIn("小时", tomorrow["remaining"])
        self.assertNotIn("23:59", str(tomorrow))

    def test_unknown_and_conflicting_dates_have_no_fabricated_countdown(self):
        self.assertEqual(self.notice(None)["label"], "截止未公布")
        self.assertIn("滚动招聘", self.notice(None, rolling=True)["label"])
        for deadline in (None, "2030-11-10"):
            with self.subTest(deadline=deadline):
                result = self.notice(deadline, status="official_conflict", outcome="verify")
                self.assertEqual(result["label"], "截止待核 · 来源冲突")
                self.assertEqual(result["remaining"], "暂不计算倒计时")
                self.assertIn("核清后", result["next_action"])

    def test_unverified_records_do_not_turn_urgency_into_permission_to_submit(self):
        result = self.notice("2030-11-10T09:00:00+08:00", status="unverified", outcome="verify")
        self.assertIn("待核", result["label"])
        self.assertIn("按待核记录计算", result["remaining"])
        self.assertIn("核对官方", result["next_action"])
        expired = self.notice("2030-11-08", status="unverified", outcome="verify")
        self.assertIn("开放状态待核", expired["remaining"])
        self.assertEqual(self.notice("2030-11-10", outcome="skip")["next_action"], "该岗位已排除，停止本岗定制。")

    def test_notice_is_first_in_packet_and_preserves_raw_deadline(self):
        data = {
            "jobs": [example(deadline="2030-11-10T09:00:00+08:00")],
            "facts": {
                "F1": {"text": "提供等效语言证明", "provenance": "user_confirmed"},
                "F2": {"text": "记录班费并公示", "provenance": "user_confirmed"},
            },
            "reviews": [application("demo-001")],
        }
        ranked = rank(data, NOW)
        self.assertEqual(ranked[0]["deadline"], data["jobs"][0]["deadline"])
        packet = render_packet(data, ranked, "demo-001")
        self.assertLess(packet.index("> **24 小时内截止**"), packet.index("**准备判断**"))
        self.assertIn("> **剩余时间** 还剩 17 小时", packet)
        self.assertIn(NOW.isoformat(), packet)


if __name__ == "__main__":
    unittest.main()
