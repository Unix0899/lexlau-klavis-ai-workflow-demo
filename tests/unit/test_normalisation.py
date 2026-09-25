import unittest

from ai.bug_replay import bug_replay
from ai.evaluation import canonical, is_correct
from ai.mock_provider import MockAIProvider, MockFallbackProvider, parse_amount, parse_date

DOC = """SYNTHETIC DEMONSTRATION DOCUMENT - FICTIONAL DATA - NOT A REAL CASE
Formal notice
Our reference: SYN-26-00042
Subject: Unpaid invoices for office furniture
On behalf of: Brightwater Interiors SRL
Counterparty: Norvale Logistics BV
Competent court: Brussels Enterprise Court
Date of incident: 14 March 2026
Reply by: 02/05/2026
Principal amount: 12.450,00 EUR
Late interest: EUR 380.50
"""


class Dates(unittest.TestCase):
    def test_formats(self):
        for raw in ("2026-03-14", "14/03/2026", "14.03.2026", "14 March 2026", "March 14, 2026"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_date(raw), ("2026-03-14", False))

    def test_incomplete_and_invalid(self):
        self.assertEqual(parse_date("May 2026"), (None, True))
        self.assertEqual(parse_date("31/02/2026"), (None, False))
        self.assertEqual(parse_date("soon"), (None, False))


class Amounts(unittest.TestCase):
    def test_formats(self):
        for raw in ("EUR 12,450.00", "12.450,00 EUR", "€ 12.450,00", "12 450,00 euros"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_amount(raw), (12450.0, "EUR"))

    def test_small_and_missing(self):
        self.assertEqual(parse_amount("EUR 980"), (980.0, "EUR"))
        self.assertEqual(parse_amount("EUR 1.5")[0], 1.5)
        self.assertEqual(parse_amount("not stated")[0], None)


class MockExtraction(unittest.TestCase):
    def test_label_variants(self):
        f = MockAIProvider().extract(DOC)["fields"]
        self.assertEqual(f["case_reference"]["value"], "SYN-26-00042")
        self.assertEqual(f["client_name"]["value"], "Brightwater Interiors SRL")
        self.assertEqual(f["opposing_party"]["value"], "Norvale Logistics BV")
        self.assertEqual(f["jurisdiction"]["value"], "Brussels Enterprise Court")
        self.assertEqual(f["document_type"]["value"], "Formal notice")
        self.assertEqual({d["label"]: d["date"] for d in f["important_dates"]["value"]},
                         {"incident_date": "2026-03-14", "response_deadline": "2026-05-02"})
        self.assertEqual({a["label"]: a["value"] for a in f["amounts"]["value"]},
                         {"amount_claimed": 12450.0, "late_interest": 380.5})

    def test_ocr_tolerant_labels_and_reference(self):
        noisy = DOC.replace("On behalf of:", "0n bchalf 0f;").replace("SYN-26-00042", "5YN-26-OO042")
        f = MockAIProvider().extract(noisy)["fields"]
        self.assertEqual(f["client_name"]["value"], "Brightwater Interiors SRL")
        self.assertEqual(f["client_name"]["method"], "ocr_tolerant_label")
        self.assertLess(f["client_name"]["confidence"], 0.8)
        self.assertEqual(f["case_reference"]["value"], "SYN-26-00042")

    def test_fallback_engine_is_stricter(self):
        noisy = DOC.replace("On behalf of:", "0n bchalf 0f;")
        f = MockFallbackProvider().extract(noisy)["fields"]
        self.assertIsNone(f["client_name"]["value"])
        self.assertLessEqual(max(v["confidence"] for v in f.values()), 0.85)

    def test_gazetteer_when_no_label(self):
        doc = DOC.replace("Competent court: Brussels Enterprise Court\n", "") + \
            "The matter may be brought before the Ghent Labour Court.\n"
        f = MockAIProvider().extract(doc)["fields"]
        self.assertEqual(f["jurisdiction"]["value"], "Ghent Labour Court")
        self.assertEqual(f["jurisdiction"]["method"], "gazetteer")

    def test_conflict_detected(self):
        doc = DOC + "Principal amount (revised): EUR 14,000.00\n"
        out = MockAIProvider().extract(doc)
        self.assertTrue(any(c["field"] == "amounts" for c in out["conflicts"]))
        self.assertLess(out["fields"]["amounts"]["confidence"], 0.7)

    def test_missing_amount_is_null_not_zero(self):
        doc = "\n".join(ln for ln in DOC.splitlines() if not ln.startswith("Principal amount"))
        amounts = MockAIProvider().extract(doc)["fields"]["amounts"]["value"]
        self.assertFalse(any(a["label"] == "amount_claimed" for a in amounts))
        with bug_replay("missing_as_zero"):  # BUG-05 replay
            amounts = MockAIProvider().extract(doc)["fields"]["amounts"]["value"]
        self.assertEqual(amounts[0], {"label": "amount_claimed", "value": 0.0, "currency": "EUR", "raw": ""})


class Evaluation(unittest.TestCase):
    def test_text_normalisation(self):
        self.assertTrue(is_correct("client_name", "brightwater  interiors srl.", "Brightwater Interiors SRL"))
        self.assertFalse(is_correct("client_name", "Brightwatcr Interiors SRL", "Brightwater Interiors SRL"))

    def test_null_equals_null(self):
        self.assertTrue(is_correct("jurisdiction", None, None))
        self.assertTrue(is_correct("amounts", [], None))

    def test_lists_ignore_order_and_raw(self):
        a = [{"label": "late_interest", "value": 10, "raw": "x"}, {"label": "amount_claimed", "value": 5.0}]
        b = [{"label": "amount_claimed", "value": 5}, {"label": "late_interest", "value": 10.0}]
        self.assertEqual(canonical("amounts", a), canonical("amounts", b))


if __name__ == "__main__":
    unittest.main()
