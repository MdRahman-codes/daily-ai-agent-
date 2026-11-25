import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import check_today


class FreshnessTests(unittest.TestCase):
    def test_current_day(self):
        now = datetime(2026, 11, 26, 1, 5, tzinfo=timezone(timedelta(hours=6)))
        self.assertTrue(check_today.is_current_day({"date": "Thursday, 26 November 2026", "business_idea": {"title": "X"}}, now))
        self.assertFalse(check_today.is_current_day({"date": "Wednesday, 25 November 2026", "business_idea": {"title": "X"}}, now))

    def test_dispatch_always_runs(self):
        with patch('check_today.request.urlopen') as get:
            self.assertFalse(check_today.should_skip("https://example.com/content.json", "workflow_dispatch"))
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
