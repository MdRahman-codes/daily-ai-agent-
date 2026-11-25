import unittest
from unittest.mock import patch

import requests
import notify


class NotifyTests(unittest.TestCase):
    def test_daily_messages_are_in_bangla(self):
        content = {
            'date_bn': 'বৃহস্পতিবার, ২৬ নভেম্বর ২০২৬',
            'business_idea': {'title': 'দোকান', 'overview': 'বাংলা বিবরণ',
                              'target_customer': 'স্থানীয় ক্রেতা', 'revenue_model': 'পণ্য বিক্রি',
                              'demand_reason': 'চাহিদা রয়েছে', 'startup_cost_bdt_min': 10000,
                              'startup_cost_bdt_max': 12000,
                              'illustrative_monthly_roi_percent': 7.5,
                              'illustrative_monthly_net_profit_bdt': 750},
            'research_paper': {'title': 'English paper title', 'title_bn': 'গবেষণার বাংলা শিরোনাম',
                               'url': 'https://arxiv.org/abs/1234.5678',
                               'summary': {'overview': 'বাংলা গবেষণার সারাংশ', 'field': 'কম্পিউটার বিজ্ঞান'}},
            'facts': [{'claim': 'প্রথম তথ্য', 'explanation': 'প্রথম ব্যাখ্যা'},
                      {'claim': 'দ্বিতীয় তথ্য', 'explanation': 'দ্বিতীয় ব্যাখ্যা'}]
        }
        messages = notify.build_messages(content)
        self.assertEqual(len(messages), 3)
        self.assertIn('৭.৫%', messages[0])
        self.assertIn('গবেষণার বাংলা শিরোনাম', messages[1])
        self.assertNotIn('English paper title', messages[1])
        self.assertNotIn('Adhuri', ''.join(messages))
        self.assertNotIn('Open briefing', ''.join(messages))

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
        notify.send_message('https://api.telegram.org/botFAKE/sendMessage', '1', 'hello')
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch('notify.requests.post')
    def test_daily_sms_has_no_inline_button(self, post):
        from unittest.mock import Mock
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"ok": True}
        post.return_value = response
        notify.send_message('https://api.telegram.org/botFAKE/sendMessage', '1', 'demo')
        payload = post.call_args.kwargs['json']
        self.assertNotIn('reply_markup', payload)
        self.assertEqual(payload['text'], 'demo')

    @patch('notify.requests.post')
    def test_do_not_truncate_html(self, post):
        with self.assertRaisesRegex(RuntimeError, "too long"):
            notify.send_message('https://api.telegram.org/botFAKE/sendMessage', '1', '<b>' + 'x' * 4000 + '</b>')
        post.assert_not_called()

    @patch('notify.requests.post')
    def test_network_error_does_not_print_bot_token(self, post):
        secret = 'FAKE_TEST_TOKEN_DO_NOT_USE'
        post.side_effect = requests.ConnectionError(f'failed URL bot{secret}/sendMessage')
        with self.assertRaises(RuntimeError) as caught:
            notify.send_message('https://api.telegram.org/bot' + secret + '/sendMessage', '1', 'hello')
        self.assertNotIn(secret, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
