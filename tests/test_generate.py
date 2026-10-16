import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate


class FakeResponse:
    def __init__(self, status_code, data=None, text='', headers=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._data


class GenerateTests(unittest.TestCase):
    def test_json_from_fenced_json(self):
        self.assertEqual(generate.json_from('```json\n{"ok": true}\n```'), {"ok": True})

    def test_json_from_extra_text(self):
        self.assertEqual(generate.json_from('Result:\n{"ok": true}\nDone'), {"ok": True})

    def test_reconstruct_abstract(self):
        data = {"hello": [0], "world": [1], "again": [2]}
        self.assertEqual(generate.reconstruct_abstract(data), "hello world again")

    @patch('generate.time.sleep')
    @patch('generate.requests.post')
    def test_503_switches_to_fallback_model(self, post, sleep):
        success = FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": '{"works": true}'}]}}]})
        post.side_effect = [
            FakeResponse(503, {"error": {"message": "temporarily unavailable"}}, text='503'),
            FakeResponse(503, {"error": {"message": "temporarily unavailable"}}, text='503'),
            success,
        ]
        with (
            patch.object(generate, 'API_KEY', 'unit-test-key'),
            patch.object(generate, 'MODEL', 'gemini-primary-test'),
            patch.object(generate, 'FALLBACK_MODELS', 'gemini-fallback-test'),
            patch.object(generate, 'RETRIES_PER_MODEL', 2),
        ):
            result = generate.gemini('Return JSON')
        self.assertEqual(json.loads(result), {"works": True})
        self.assertEqual(post.call_count, 3)
        self.assertIn('/models/gemini-primary-test:generateContent', post.call_args_list[0].args[0])
        self.assertIn('/models/gemini-fallback-test:generateContent', post.call_args_list[2].args[0])
        self.assertNotIn('temperature', post.call_args_list[0].kwargs['json']['generationConfig'])
        self.assertEqual(post.call_args_list[0].kwargs['headers']['x-goog-api-key'], 'unit-test-key')

    @patch('generate.requests.get')
    @patch('generate.gemini')
    @patch('generate.get_research_paper')
    def test_main_writes_complete_payload(self, research, gemini_call, requests_get):
        research.return_value = {
            "title": "Example paper", "abstract": "Example abstract", "url": "https://arxiv.org/abs/1234.5678",
            "authors": ["Author"], "published": "2026-10-01", "metadata_source": "arXiv API",
            "summary": {"overview": "A safe overview.", "key_findings": ["One", "Two"], "field": "CSE"}
        }
        generated = {
            "business_idea": {
                "title": "Example", "overview": "Brief idea", "problem": "Problem", "target_customer": "Learners",
                "revenue_model": "Subscription", "first_step": "Interview users", "risks": "Competition", "confidence_note": "No guarantee"
            },
            "facts": [
                {"claim": "Fact one", "explanation": "Explanation one.", "source_url": "", "source_verified": False},
                {"claim": "Fact two", "explanation": "Explanation two.", "source_url": "", "source_verified": False}
            ]
        }
        review = {"facts": [
            {"status": "uncertain", "safer_wording": "Fact one", "reason": "Test"},
            {"status": "uncertain", "safer_wording": "Fact two", "reason": "Test"}
        ]}
        gemini_call.side_effect = [json.dumps(generated), json.dumps(review)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(generate, 'SITE', Path(tmp)):
            generate.main()
            payload = json.loads((Path(tmp) / 'content.json').read_text(encoding='utf-8'))
            self.assertEqual(len(payload['facts']), 2)
            self.assertEqual(payload['business_idea']['title'], 'Example')
            self.assertEqual(payload['research_paper']['metadata_source'], 'arXiv API')
            self.assertTrue((Path(tmp) / 'index.html').is_file())
            self.assertTrue((Path(tmp) / 'config.js').is_file())
        self.assertEqual(gemini_call.call_count, 2)
        requests_get.assert_not_called()

    def test_model_chain_removes_duplicates(self):
        with (
            patch.object(generate, 'MODEL', 'one'),
            patch.object(generate, 'FALLBACK_MODELS', 'two,one,three'),
        ):
            self.assertEqual(generate.model_chain(), ['one', 'two', 'three'])


if __name__ == '__main__':
    unittest.main()
