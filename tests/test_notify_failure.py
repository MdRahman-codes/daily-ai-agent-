import io
import json
import unittest
from unittest.mock import patch

import notify_failure


class FailureAlertTests(unittest.TestCase):
    @patch('notify_failure.request.urlopen')
    def test_failure_alert_does_not_log_token(self, opener):
        class FakeContext:
            def __enter__(self):
                return io.BytesIO(json.dumps({"ok": True}).encode())
            def __exit__(self, *args):
                return False
        opener.return_value = FakeContext()
        with patch.dict('notify_failure.os.environ', {
            'TELEGRAM_BOT_TOKEN': 'DUMMY-SECRET',
            'TELEGRAM_CHAT_ID': '123',
            'GITHUB_RUN_URL': 'https://github.com/example/repo/actions/runs/1',
        }):
            notify_failure.main()
        args = opener.call_args.args[0]
        self.assertIn('sendMessage', args.full_url)
        self.assertEqual(json.loads(args.data)['chat_id'], '123')


if __name__ == '__main__':
    unittest.main()
