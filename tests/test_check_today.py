import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import check_today


BDT = timezone(timedelta(hours=6))
NOW = datetime(2026, 11, 26, 17, 45, tzinfo=BDT)


def run(run_id, *, kind="schedule", status="completed", created="2026-11-26T09:21:50Z"):
    return {
        "id": run_id,
        "name": "Daily AI Agent",
        "event": kind,
        "status": status,
        "created_at": created,
        "conclusion": "success",
    }


class DeliveryHistoryTests(unittest.TestCase):
    def test_bangladesh_date_conversion(self):
        self.assertEqual(check_today.bangladesh_day("2026-11-25T20:10:00Z"), "2026-11-26")
        self.assertEqual(check_today.bangladesh_day("2026-11-26T09:21:50Z"), "2026-11-26")

    def test_scheduled_run_without_successful_notification_is_not_skipped(self):
        with patch("check_today.api_json", side_effect=[
            {"workflow_runs": [run(100)]},
            {"jobs": [
                {"name": "build", "conclusion": "success"},
                {"name": "deploy", "conclusion": "skipped"},
                {"name": "notify", "conclusion": "skipped"},
            ]},
        ]) as api:
            self.assertFalse(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))
        self.assertEqual(api.call_count, 2)

    def test_skip_only_after_successful_scheduled_notification(self):
        with patch("check_today.api_json", side_effect=[
            {"workflow_runs": [run(100)]},
            {"jobs": [{"name": "notify", "conclusion": "success"}]},
        ]):
            self.assertTrue(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))

    def test_manual_demo_notification_does_not_suppress_morning(self):
        with patch("check_today.api_json", return_value={
            "workflow_runs": [run(100, kind="workflow_dispatch")]
        }) as api:
            self.assertFalse(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))
        self.assertEqual(api.call_count, 1)

    def test_previous_day_delivery_does_not_suppress_today(self):
        with patch("check_today.api_json", return_value={
            "workflow_runs": [run(100, created="2026-11-25T09:21:50Z")]
        }) as api:
            self.assertFalse(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))
        self.assertEqual(api.call_count, 1)

    def test_current_run_is_not_considered_delivered(self):
        with patch("check_today.api_json", return_value={
            "workflow_runs": [run(101)]
        }) as api:
            self.assertFalse(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))
        self.assertEqual(api.call_count, 1)

    def test_failed_api_prefers_delivery_over_silent_skip(self):
        with patch("check_today.api_json", side_effect=OSError("temporary")):
            self.assertFalse(check_today.should_skip(
                "schedule", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))

    def test_manual_dispatch_always_runs_without_api(self):
        with patch("check_today.api_json") as api:
            self.assertFalse(check_today.should_skip(
                "workflow_dispatch", "MdRahman-codes/daily-ai-agent-", "fake", "101", now=NOW
            ))
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
