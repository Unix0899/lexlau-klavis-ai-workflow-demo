"""End-to-end through HTTP: the real server on a free port, a temporary database."""
import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from ai import safe_logging
from app.backend import server, services

FIX = Path(__file__).resolve().parents[1] / "fixtures"


class HttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.patch = mock.patch.object(safe_logging, "LOG_PATH", Path(cls.tmp.name) / "app.log")
        cls.patch.start()
        cls.upload_patch = mock.patch.object(services, "UPLOAD_DIR", Path(cls.tmp.name) / "uploads")
        cls.upload_patch.start()
        server.CONN = services.init_db(Path(cls.tmp.name) / "api.sqlite")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.CONN.close()
        cls.patch.stop()
        cls.upload_patch.stop()
        cls.tmp.cleanup()

    def call(self, path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if data else "GET"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if resp.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def upload(self, name, **extra):
        b64 = base64.b64encode((FIX / name).read_bytes()).decode()
        return self.call("/api/extract", {"filename": name, "content_base64": b64, **extra})

    def test_frontend_shows_disclosure(self):
        status, html = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Synthetic demonstration data.", html)
        self.assertIn(b"No real client, legal-case or confidential LexLau/Klavis data is included.", html)

    def test_meta_notices(self):
        _, meta = self.call("/api/meta")
        self.assertEqual(meta["ai_notice"], "AI-generated draft for demonstration purposes. Human validation required.")
        self.assertEqual(meta["assistant_notice"], "Demo assistant — not legal advice.")
        self.assertEqual(meta["provider_chain"], ["mock-primary", "mock-fallback"])

    def test_full_workflow_over_http(self):
        status, out = self.upload("clean_letter.docx")
        self.assertEqual((status, out["status"]), (200, "success"))
        self.assertEqual(out["notice"], "AI-generated draft for demonstration purposes. Human validation required.")
        run_id = out["ai_run_id"]
        _, draft = self.call(f"/api/runs/{run_id}")
        fields = {k: v["value"] for k, v in draft["fields"].items()}
        fields["client_name"] = fields["client_name"] + " (checked)"

        status, err = self.call("/api/cases", {"ai_run_id": run_id, "fields": fields, "validated": False})
        self.assertEqual((status, err["error_code"]), (400, "VALIDATION_REQUIRED"))

        body = {"ai_run_id": run_id, "fields": fields, "validated": True, "idempotency_key": "http-1"}
        status, created = self.call("/api/cases", body)
        self.assertEqual((status, created["status"], created["fields_corrected"]), (201, "created", 1))
        status, again = self.call("/api/cases", body)  # double click
        self.assertEqual((status, again["status"], again["case_id"]), (200, "existing", created["case_id"]))

        _, detail = self.call(f"/api/cases/{created['case_id']}")
        self.assertTrue(detail["case"]["client_name"].endswith("(checked)"))
        _, summary = self.call(f"/api/cases/{created['case_id']}/summary", {})
        self.assertIn("Human validation required", summary["notice"])
        _, answer = self.call(f"/api/cases/{created['case_id']}/ask", {"question": "What parties were identified?"})
        self.assertIn("(checked)", answer["answer"])
        self.assertIn("not legal advice", answer["notice"])

        status, dup = self.upload("clean_letter.docx")
        status, blocked = self.call("/api/cases", {"ai_run_id": dup["ai_run_id"], "fields": fields,
                                                   "validated": True, "idempotency_key": "http-2"})
        self.assertEqual((status, blocked["error_code"]), (409, "DUPLICATE_CASE"))

    def test_fallback_and_outage_over_http(self):
        status, out = self.upload("clean_notice.pdf", simulate="primary_down")
        self.assertEqual((status, out["provider_used"], out["fallback_used"]), (200, "mock-fallback", True))
        status, out = self.upload("clean_notice.pdf", simulate="all_down")
        self.assertEqual((status, out["error_code"]), (503, "AI_UNAVAILABLE"))

    def test_invalid_and_oversized_uploads(self):
        status, out = self.upload("renamed_executable.docx")
        self.assertEqual((status, out["error_code"]), (415, "UNSUPPORTED_FORMAT"))
        big = base64.b64encode(b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024)).decode()
        status, out = self.call("/api/extract", {"filename": "big.pdf", "content_base64": big})
        self.assertEqual((status, out["error_code"]), (413, "FILE_TOO_LARGE"))

    def test_invalid_category_rejected(self):
        status, out = self.call("/api/cases", {"ai_run_id": 1, "fields": {"case_category": "Tax"}, "validated": True})
        self.assertEqual((status, out["error_code"]), (422, "INVALID_CATEGORY"))

    def test_request_log_is_metadata_only(self):
        self.call("/api/cases?search=Brightwater")
        lines = [json.loads(x) for x in safe_logging.LOG_PATH.read_text(encoding="utf-8").splitlines()]
        requests = [x for x in lines if x["event_type"] == "http_request"]
        self.assertTrue(requests)
        self.assertTrue(all("?" not in x["path"] for x in requests))  # no query string (search terms)
        self.assertNotIn("Brightwater", safe_logging.LOG_PATH.read_text(encoding="utf-8"))

    def test_unknown_endpoint_and_errors_are_structured(self):
        status, out = self.call("/api/nothing")
        self.assertEqual((status, out["status"]), (404, "error"))
        status, out = self.call("/api/cases/999999")
        self.assertEqual((status, out["error_code"]), (404, "CASE_NOT_FOUND"))


if __name__ == "__main__":
    unittest.main()
