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
    def test_bengali_date(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 11, 26, 7, tzinfo=timezone(timedelta(hours=6)))
        self.assertEqual(generate.bangla_date(now), 'বৃহস্পতিবার, ২৬ নভেম্বর ২০২৬')

    def test_reject_english_only_business(self):
        with self.assertRaisesRegex(RuntimeError, 'Bengali'):
            generate.validate_bangla_briefing({'title': 'Only English'}, {}, [])

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
            "summary": {"title_bn": "গবেষণার উদাহরণ", "overview": "নিরাপদ গবেষণার ব্যাখ্যা", "key_findings": ["প্রথম বিষয়", "দ্বিতীয় বিষয়"], "field": "কম্পিউটার বিজ্ঞান", "reading_level": "মধ্যম", "limitations": "সীমাবদ্ধতার কথা উল্লেখ নেই", "practical_relevance": "বাস্তবে প্রয়োগের সুযোগ আছে"}
        }
        generated = {
            "business_idea": {
                "title": "দোকানের ধারণা", "category": "খুচরা ব্যবসা", "overview": "ব্যবসার বিবরণ", "problem": "ব্যবসার সমস্যা", "target_customer": "স্থানীয় ক্রেতা",
                "revenue_model": "পণ্য বিক্রি", "first_step": "চাহিদা যাচাই", "risks": "প্রতিযোগিতা", "confidence_note": "লাভের নিশ্চয়তা নেই",
                "demand_reason": "নিত্যপ্রয়োজন", "validation_plan": "ছোট পরিসরে পরীক্ষা",
                "startup_cost_breakdown": [{"item": "সরঞ্জাম", "estimated_bdt": 10000}, {"item": "ভাড়া", "estimated_bdt": 5000}, {"item": "পণ্য", "estimated_bdt": 20000}]
            },
            "facts": [
                {"claim": "প্রথম তথ্য", "explanation": "প্রথম ব্যাখ্যা।", "source_url": "", "source_verified": False},
                {"claim": "দ্বিতীয় তথ্য", "explanation": "দ্বিতীয় ব্যাখ্যা।", "source_url": "", "source_verified": False}
            ]
        }
        review = {"facts": [
            {"status": "uncertain", "safer_wording": "প্রথম তথ্য", "reason": "অনিশ্চিত"},
            {"status": "uncertain", "safer_wording": "দ্বিতীয় তথ্য", "reason": "অনিশ্চিত"}
        ]}
        gemini_call.side_effect = [json.dumps(generated), json.dumps(review)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(generate, 'SITE', Path(tmp)):
            generate.main()
            payload = json.loads((Path(tmp) / 'content.json').read_text(encoding='utf-8'))
            self.assertEqual(len(payload['facts']), 2)
            self.assertEqual(payload['business_idea']['title'], 'দোকানের ধারণা')
            self.assertEqual(payload['research_paper']['summary']['title_bn'], 'গবেষণার উদাহরণ')
            self.assertIn('নভেম্বর', payload['date_bn'])
            self.assertEqual(payload['business_idea']['startup_cost_bdt_min'], 35000)
            self.assertEqual(payload['business_idea']['startup_cost_bdt_max'], 42000)
            self.assertEqual(payload['research_paper']['metadata_source'], 'arXiv API')
            self.assertTrue((Path(tmp) / 'index.html').is_file())
            self.assertFalse((Path(tmp) / 'config.js').exists())
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

    def test_roi_is_derived_from_revenue_and_expenses(self):
        idea = {"startup_cost_breakdown": [
            {"item": "Stock", "estimated_bdt": 30000},
            {"item": "Equipment", "estimated_bdt": 20000},
            {"item": "Rent", "estimated_bdt": 10000},
        ], "illustrative_monthly_revenue_bdt": 40000,
           "illustrative_monthly_expenses_bdt": 34000,
           "illustrative_monthly_roi_percent": 95.0}
        generate.calculate_startup_costs(idea)
        self.assertEqual(idea["illustrative_monthly_net_profit_bdt"], 6000)
        self.assertEqual(idea["illustrative_monthly_roi_percent"], 10.0)
        self.assertIsNone(idea["success_probability"])

    def test_roi_allows_negative_returns(self):
        idea = {"startup_cost_breakdown": [
            {"item": "Stock", "estimated_bdt": 30000},
            {"item": "Tools", "estimated_bdt": 10000},
            {"item": "Rent", "estimated_bdt": 10000},
        ], "illustrative_monthly_revenue_bdt": 25000,
           "illustrative_monthly_expenses_bdt": 30000}
        generate.calculate_startup_costs(idea)
        self.assertEqual(idea["illustrative_monthly_roi_percent"], -10.0)

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
