import unittest
from unittest.mock import patch
import adhuri_poll as bot

FIELDS = {"meaning_bn": "নিরাপদ", "part_of_speech": "Adjective",
          "grammatical_function_bn": "বিশেষণ", "real_life_use_bn": "A secure door — নিরাপদ দরজা",
          "sentence_context_bn": "The door is secure — নিরাপত্তার অবস্থা"}


class BotTests(unittest.TestCase):
    def test_word_fields_are_in_required_order(self):
        s = bot.word_reply("secure", FIELDS)
        labels = ("বাংলা অর্থ", "Parts of Speech", "Grammatical Function",
                  "বাস্তব জীবনে ব্যবহার", "বাক্যে ব্যবহার ও প্রসঙ্গ")
        self.assertEqual(sorted(s.index(x) for x in labels), [s.index(x) for x in labels])

    def test_html_escape(self):
        obj = {k: "<script>x</script> নিরাপদ" for k in FIELDS}
        s = bot.word_reply("<test>", obj)
        self.assertNotIn("<script>", s)
        self.assertIn("&lt;script&gt;", s)

    @patch("adhuri_poll.gemini_json", return_value=FIELDS)
    def test_one_word_uses_vocabulary(self, api):
        self.assertIn("বাংলা অর্থ", bot.answer("secure"))
        self.assertEqual(api.call_count, 1)

    @patch("adhuri_poll.context", return_value="{}")
    @patch("adhuri_poll.gemini_json", return_value={"reply_bn": "হ্যাঁ, সম্ভব।"})
    def test_questions_require_bangla(self, gen, ctx):
        self.assertIn("সম্ভব", bot.answer("How do I plan a business?"))
        self.assertIn("ALWAYS IN BANGLA", gen.call_args.args[0])

    @patch("adhuri_poll.context", return_value="{}")
    @patch("adhuri_poll.gemini_json", return_value={"reply_bn": "English only."})
    def test_non_bangla_answer_is_refused(self, gen, ctx):
        with self.assertRaisesRegex(RuntimeError, "Bangla"):
            bot.answer("How do I plan a business?")

    @patch("adhuri_poll.api")
    def test_unauthorized_chat_ignored(self, req):
        with patch.object(bot, "OWNER", "7"):
            bot.process({"message": {"chat": {"id": 8, "type": "private"}, "text": "word"}})
        req.assert_not_called()

    @patch("adhuri_poll.api")
    @patch("adhuri_poll.answer", return_value="বাংলা উত্তর")
    def test_reply_in_inbox_not_inline_keyboard(self, gen, req):
        with patch.object(bot, "OWNER", "7"):
            bot.process({"message": {"chat": {"id": 7, "type": "private"}, "text": "question"}})
        self.assertNotIn("reply_markup", req.call_args.kwargs)
        self.assertEqual(req.call_args.kwargs["text"], "বাংলা উত্তর")

    @patch("adhuri_poll.api", return_value={"url": "https://already-set.example/"})
    def test_existing_webhook_is_not_destroyed(self, req):
        with patch.object(bot, "TOKEN", "fake"), patch.object(bot, "OWNER", "7"):
            bot.main()
        self.assertEqual(req.call_count, 1)


if __name__ == "__main__":
    unittest.main()
