import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import check_today

BDT = timezone(timedelta(hours=6))
MORNING = datetime(2026, 11, 27, 7, 5, tzinfo=BDT)
LATE = datetime(2026, 11, 27, 7, 31, tzinfo=BDT)


def record(run_id, event="push", status="completed",
           created="2026-11-27T01:02:00Z"):
    return {
        "id": run_id, "name": "Daily AI Agent", "event": event,
        "status": status, "created_at": created, "conclusion": "success",
    }


class MorningDeliveryTests(unittest.TestCase):
    def test_local_window_start(self):
        self.assertTrue(check_today.in_delivery_window(
            datetime(2026, 11, 27, 7, tzinfo=BDT)))

    def test_local_window_end(self):
        self.assertTrue(check_today.in_delivery_window(
            datetime(2026, 11, 27, 7, 29, 59, tzinfo=BDT)))
        self.assertFalse(check_today.in_delivery_window(LATE))

    def test_nighttime_push_does_not_send_telegram(self):
        with patch("check_today.api_json") as api:
            self.assertTrue(check_today.should_skip("push", "owner/repo", "token",
                                                    "2", now=datetime(
                                                        2026, 11, 26, 19, tzinfo=BDT)))
        api.assert_not_called()

    def test_late_github_cron_skips(self):
        with patch("check_today.api_json") as api:
            self.assertTrue(check_today.should_skip(
                "schedule", "owner/repo", "token", "2", now=LATE))
        api.assert_not_called()

    def test_morning_push_runs_when_not_sent(self):
        with patch("check_today.api_json", return_value={"workflow_runs": []}):
            self.assertFalse(check_today.should_skip(
                "push", "owner/repo", "token", "2", now=MORNING))

    def test_successful_push_prevents_duplicate_scheduled_run(self):
        with patch("check_today.api_json", side_effect=[
            {"workflow_runs": [record(1)]},
            {"jobs": [{"name": "notify", "conclusion": "success"}]},
        ]) as api:
            self.assertTrue(check_today.should_skip(
                "schedule", "owner/repo", "token", "2", now=MORNING))
        self.assertEqual(api.call_count, 2)

    def test_successful_schedule_prevents_duplicate_push(self):
        with patch("check_today.api_json", side_effect=[
            {"workflow_runs": [record(1, event="schedule")]},
            {"jobs": [{"name": "notify", "conclusion": "success"}]},
        ]):
            self.assertTrue(check_today.should_skip(
                "push", "owner/repo", "token", "2", now=MORNING))

    def test_demo_workflow_does_not_suppress_morning(self):
        with patch("check_today.api_json", return_value={
            "workflow_runs": [record(1, event="workflow_dispatch")]
        }):
            self.assertFalse(check_today.should_skip(
                "schedule", "owner/repo", "token", "2", now=MORNING))

    def test_skipped_notification_does_not_count_as_delivery(self):
        with patch("check_today.api_json", side_effect=[
            {"workflow_runs": [record(1)]},
            {"jobs": [{"name": "notify", "conclusion": "skipped"}]},
        ]):
            self.assertFalse(check_today.should_skip(
                "push", "owner/repo", "token", "2", now=MORNING))

    def test_manual_dispatch_is_allowed_outside_window(self):
        with patch("check_today.api_json") as api:
            self.assertFalse(check_today.should_skip(
                "workflow_dispatch", "owner/repo", "token", "2", now=LATE))
        api.assert_not_called()

    def test_api_failure_prefers_attempt(self):
        with patch("check_today.api_json", side_effect=OSError("fail")):
            self.assertFalse(check_today.should_skip(
                "push", "owner/repo", "token", "2", now=MORNING))

    def test_bangladesh_day_from_utc(self):
        self.assertEqual(check_today.bangladesh_day("2026-11-26T19:02:00Z"),
                         "2026-11-27")

    def test_current_run_is_ignored(self):
        with patch("check_today.api_json", return_value={
            "workflow_runs": [record(2)]
        }) as api:
            self.assertFalse(check_today.should_skip(
                "push", "owner/repo", "token", "2", now=MORNING))
        self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
