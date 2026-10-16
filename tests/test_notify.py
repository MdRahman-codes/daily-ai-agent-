import unittest
from unittest.mock import patch

import requests
import notify


class NotifyTests(unittest.TestCase):
    def test_safe_text_escapes_html(self):
        self.assertEqual(notify.safe_text('<hello & "world">'), '&lt;hello &amp; &quot;world&quot;&gt;')

    @patch('notify.requests.post')
    def test_network_error_does_not_print_bot_token(self, post):
        secret = 'FAKE_TEST_TOKEN_DO_NOT_USE'
        post.side_effect = requests.ConnectionError(f'failed URL bot{secret}/sendMessage')
        with self.assertRaises(RuntimeError) as caught:
            notify.send_message('https://api.telegram.org/bot' + secret + '/sendMessage', '1', 'hello', {})
        self.assertNotIn(secret, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
