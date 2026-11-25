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
                "revenue_model": "Subscription", "first_step": "Interview users", "risks": "Competition", "confidence_note": "No guarantee",
                "startup_cost_breakdown": [{"item": "Tools", "estimated_bdt": 10000}, {"item": "Rent", "estimated_bdt": 5000}, {"item": "Stock", "estimated_bdt": 20000}]
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
            self.assertEqual(payload['business_idea']['startup_cost_bdt_min'], 35000)
            self.assertEqual(payload['business_idea']['startup_cost_bdt_max'], 42000)
            self.assertEqual(payload['research_paper']['metadata_source'], 'arXiv API')
            self.assertTrue((Path(tmp) / 'index.html').is_file())
            self.assertTrue((Path(tmp) / 'config.js').is_file())
        self.assertEqual(gemini_call.call_count, 2)
        requests_get.assert_not_called()

    def test_review_blocks_likely_inaccurate_facts(self):
        facts = [{"claim": "False", "source_verified": True}, {"claim": "True"}]
        reviews = {"facts": [
            {"status": "likely inaccurate", "safer_wording": "", "reason": "False claim"},
            {"status": "uncertain", "safer_wording": "Maybe", "reason": "Unverified"},
        ]}
        with self.assertRaisesRegex(RuntimeError, "likely inaccurate"):
            generate.validate_fact_review(facts, reviews)

    def test_review_fails_closed_on_missing_results(self):
        with self.assertRaisesRegex(RuntimeError, "exactly two"):
            generate.validate_fact_review([{}, {}], {"facts": []})

    def test_url_validation_rejects_internal_addresses(self):
        self.assertEqual(generate.clean_https_url("https://127.0.0.1/private"), "")
        self.assertEqual(generate.clean_https_url("https://169.254.169.254/latest"), "")
        self.assertEqual(generate.clean_https_url("https://localhost/private"), "")
        self.assertFalse(generate.safe_probe("https://evil.example/path"))
        self.assertTrue(generate.safe_probe("https://www.nasa.gov/path"))

    @patch('generate.requests.get')
    def test_fact_source_does_not_request_untrusted_host(self, get):
        facts = [{"claim": "c", "source_url": "https://evil.example/x", "source_verified": True}]
        generate.check_fact_sources(facts)
        get.assert_not_called()
        self.assertFalse(facts[0]["source_verified"])

    @patch('generate.gemini')
    def test_json_response_repaired_after_non_object(self, gemini):
        gemini.side_effect = ['[]', '{"ok": true}']
        self.assertEqual(generate.gemini_json("JSON"), {"ok": True})
        self.assertEqual(gemini.call_count, 2)

    def test_computing_topic_filter(self):
        self.assertTrue(generate.is_computing_title("Software engineering for secure web systems"))
        self.assertFalse(generate.is_computing_title("Organic farming profitability in rural villages"))
        self.assertFalse(generate.is_computing_title("A clinical trial of a new medicine"))

    def test_budget_is_computed_not_model_claimed(self):
        idea = {"startup_cost_breakdown": [
            {"item": "Equipment", "estimated_bdt": 20000},
            {"item": "Stock", "estimated_bdt": 10000},
            {"item": "Rent", "estimated_bdt": 5000}
        ], "success_probability": "95%"}
        generate.calculate_startup_costs(idea)
        self.assertEqual(idea["startup_cost_bdt_min"], 35000)
        self.assertEqual(idea["startup_cost_bdt_max"], 42000)
        self.assertIsNone(idea["success_probability"])

    def test_budget_rejects_bad_types(self):
        with self.assertRaisesRegex(RuntimeError, "integer"):
            generate.calculate_startup_costs({"startup_cost_breakdown": [
                {"item": "A", "estimated_bdt": "2000"},
                {"item": "B", "estimated_bdt": 5000},
                {"item": "C", "estimated_bdt": 1000}
            ]})

    def test_business_sectors_include_offline_options(self):
        self.assertIn("neighborhood grocery or essential retail", generate.BUSINESS_SECTORS)
        self.assertIn("technology services or online businesses", generate.BUSINESS_SECTORS)
        self.assertGreater(len(generate.BUSINESS_SECTORS), 10)

    def test_model_chain_removes_duplicates(self):
        with (
            patch.object(generate, 'MODEL', 'one'),
            patch.object(generate, 'FALLBACK_MODELS', 'two,one,three'),
        ):
            self.assertEqual(generate.model_chain(), ['one', 'two', 'three'])


if __name__ == '__main__':
    unittest.main()
