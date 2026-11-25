import unittest
from unittest.mock import patch

import requests
import notify


class NotifyTests(unittest.TestCase):
    def test_safe_text_escapes_html(self):
        self.assertEqual(notify.safe_text('<hello & "world">'), '&lt;hello &amp; &quot;world&quot;&gt;')

    @patch('notify.time.sleep')
    @patch('notify.requests.post')
    def test_retry_on_429(self, post, sleep):
        from unittest.mock import Mock
        throttled = Mock(ok=False, status_code=429)
        throttled.json.return_value = {"ok": False, "error_code": 429, "parameters": {"retry_after": 1}}
        success = Mock(ok=True, status_code=200)
        success.json.return_value = {"ok": True}
        post.side_effect = [throttled, success]
        notify.send_message('https://api.telegram.org/botFAKE/sendMessage', '1', 'hello', {})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch('notify.requests.post')
    def test_do_not_truncate_html(self, post):
        with self.assertRaisesRegex(RuntimeError, "too long"):
            notify.send_message('https://api.telegram.org/botFAKE/sendMessage', '1', '<b>' + 'x' * 4000 + '</b>', {})
        post.assert_not_called()

    @patch('notify.requests.post')
    def test_network_error_does_not_print_bot_token(self, post):
        secret = 'FAKE_TEST_TOKEN_DO_NOT_USE'
        post.side_effect = requests.ConnectionError(f'failed URL bot{secret}/sendMessage')
        with self.assertRaises(RuntimeError) as caught:
            notify.send_message('https://api.telegram.org/bot' + secret + '/sendMessage', '1', 'hello', {})
        self.assertNotIn(secret, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
