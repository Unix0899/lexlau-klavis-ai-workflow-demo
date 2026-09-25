"""Category suggestion, fallback chain, external providers without key, summary and assistant."""
import os
import unittest
from unittest import mock

from ai.assistant import ask
from ai.bug_replay import bug_replay
from ai.category_suggestion import suggest_category
from ai.config import AI_DRAFT_NOTICE, ASSISTANT_NOTICE
from ai.external_providers import AnthropicProvider, OpenAIProvider
from ai.fallback import run_with_fallback
from ai.mock_provider import MockAIProvider, MockFallbackProvider
from ai.provider_interface import InvalidProviderOutput, validate_extraction_output
from ai.summarisation import generate_case_summary

TEXT = "Matter: Unpaid invoices\nClient: Oakhaven Retail SA\nThe invoices remain unpaid despite reminders."
CASE = {"case_title": "Unpaid invoices for IT hardware", "client_name": "Oakhaven Retail SA",
        "opposing_party": "Veldon Print NV", "case_category": "Commercial dispute",
        "jurisdiction": "Ghent Enterprise Court",
        "important_dates": [{"label": "response_deadline", "date": "2026-05-02"}],
        "amounts": [{"label": "amount_claimed", "value": 8200.0, "currency": "EUR"}],
        "missing_fields": []}


class Category(unittest.TestCase):
    def test_taxonomy(self):
        self.assertEqual(suggest_category("The employee contests the dismissal and the notice period")["category"],
                         "Employment matter")
        self.assertEqual(suggest_category("The municipality refused the permit")["category"], "Administrative matter")

    def test_no_keyword_is_other_with_low_confidence(self):
        out = suggest_category("Request for a copy of a mediation record.")
        self.assertEqual((out["category"], out["confidence"]), ("Other", 0.40))

    def test_word_boundary_and_bug02_replay(self):
        text = "Unpaid invoices for cardboard packaging. The cardboard, cardboard trays, cardboard crates " \
               "and cardboard sleeves; cardboard boxes and cardboard specification. Related invoices."
        self.assertEqual(suggest_category(text)["category"], "Commercial dispute")
        with bug_replay("category_substring"):
            self.assertEqual(suggest_category(text)["category"], "Corporate matter")


class Fallback(unittest.TestCase):
    def chain(self):
        return [MockAIProvider(), MockFallbackProvider()]

    def test_primary_success(self):
        r = run_with_fallback("extract", self.chain(), TEXT)
        self.assertEqual((r["status"], r["provider_used"], r["fallback_used"]), ("success", "mock-primary", False))

    def test_each_failure_type_falls_back(self):
        for code in ("PROVIDER_TIMEOUT", "PROVIDER_ERROR", "INVALID_OUTPUT"):
            with self.subTest(code=code):
                r = run_with_fallback("extract", self.chain(), TEXT, simulate={"mock-primary": code})
                self.assertEqual((r["provider_used"], r["fallback_used"], r["fallback_reason"]),
                                 ("mock-fallback", True, code))
                self.assertEqual([a["status"] for a in r["attempts"]], ["failed", "success"])

    def test_structured_error_when_all_fail(self):
        r = run_with_fallback("extract", self.chain(), TEXT,
                              simulate={"mock-primary": "PROVIDER_ERROR", "mock-fallback": "PROVIDER_TIMEOUT"})
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["error_code"], "AI_UNAVAILABLE")
        self.assertIn("Nothing was saved", r["message"])
        self.assertIsNone(r["provider_used"])

    def test_bug04_replay_mislabels_provider(self):
        with bug_replay("fallback_mislabel"):
            r = run_with_fallback("extract", self.chain(), TEXT, simulate={"mock-primary": "PROVIDER_TIMEOUT"})
        self.assertEqual((r["provider_used"], r["fallback_used"]), ("mock-primary", False))

    def test_contract_validation(self):
        with self.assertRaises(InvalidProviderOutput):
            validate_extraction_output({"fields": {"case_title": {"value": 3, "confidence": 0.9}}})


class ExternalProviders(unittest.TestCase):
    def test_no_key_means_unavailable_then_mock_fallback(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            for provider in (OpenAIProvider(), AnthropicProvider()):
                with self.subTest(provider=provider.name):
                    r = run_with_fallback("extract", [provider, MockAIProvider()], TEXT)
                    self.assertEqual(r["attempts"][0]["error_code"], "PROVIDER_UNAVAILABLE")
                    self.assertEqual(r["provider_used"], "mock-primary")

    def test_no_network_call_without_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), \
                mock.patch("urllib.request.urlopen") as urlopen:
            run_with_fallback("extract", [AnthropicProvider(), MockAIProvider()], TEXT)
        urlopen.assert_not_called()


class SummaryAndAssistant(unittest.TestCase):
    def test_summary_has_notice_and_uses_structured_fields(self):
        r = generate_case_summary(CASE, providers=[MockAIProvider()])
        self.assertEqual(r["notice"], AI_DRAFT_NOTICE)
        self.assertIn("Oakhaven Retail SA", r["summary"])
        self.assertIn("8,200.00", r["summary"])

    def test_assistant_answers_and_refuses_advice(self):
        self.assertIn("Veldon Print NV", ask("What parties were identified?", CASE, [MockAIProvider()])["answer"])
        self.assertIn("2026-05-02", ask("What important dates were detected?", CASE, [MockAIProvider()])["answer"])
        self.assertIn("No required field is missing", ask("Which information is still missing?", CASE,
                                                          [MockAIProvider()])["answer"])
        r = ask("Should I sue them, will we win?", CASE, [MockAIProvider()])
        self.assertIn("can't give legal advice", r["answer"])
        self.assertEqual(r["notice"], ASSISTANT_NOTICE)

    def test_empty_question(self):
        self.assertEqual(ask("   ", CASE)["error_code"], "EMPTY_QUESTION")


if __name__ == "__main__":
    unittest.main()
