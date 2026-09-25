import json
import tempfile
import unittest
from pathlib import Path

from ai.safe_logging import MAX_VALUE_CHARS, log_event, redact_text, sanitize


class Redaction(unittest.TestCase):
    def test_patterns(self):
        text = "Mail jane.doe@example.test, call +32 470 12 34 56, IBAN BE68 5390 0754 7034, NN 85.07.30-033.61"
        out = redact_text(text)
        for secret in ("jane.doe@example.test", "470 12 34 56", "BE68 5390", "85.07.30-033.61"):
            self.assertNotIn(secret, out)
        self.assertIn("[REDACTED_EMAIL]", out)
        self.assertIn("[REDACTED_IBAN]", out)

    def test_allow_list_drops_content_keys(self):
        clean = sanitize({"document_id": 4, "format": "pdf", "text": "full document", "full_document_content": "x",
                          "client_secret": "abc", "extracted_fields": {"a": 1}})
        self.assertEqual(clean, {"document_id": 4, "format": "pdf", "dropped_keys": 4})

    def test_long_values_truncated_and_structures_omitted(self):
        clean = sanitize({"error_code": "E" * 500, "provider": ["a", "b"]})
        self.assertLessEqual(len(clean["error_code"]), MAX_VALUE_CHARS + 20)
        self.assertEqual(clean["provider"], "[list omitted]")

    def test_log_file_contains_metadata_only(self):
        canary = "CANARY-CONFIDENTIAL-PARAGRAPH"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            log_event("ai_extraction_completed", log_path=path, document_id=7, format="pdf", latency_ms=12.5,
                      provider="mock-primary", document_text=canary, summary=canary)
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn(canary, json.dumps(record))
        self.assertEqual(record["document_id"], 7)
        self.assertEqual(record["dropped_keys"], 2)


if __name__ == "__main__":
    unittest.main()
