"""Workflow + database: upload -> AI -> human validation -> case, on a temporary database."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai import safe_logging
from ai.mock_provider import MockAIProvider
from app.backend import services

FIX = Path(__file__).resolve().parents[1] / "fixtures"
EXPECTED = json.loads((FIX / "expected.json").read_text(encoding="utf-8"))["fixtures"]


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "app.log"
        self.patch = mock.patch.object(safe_logging, "LOG_PATH", self.log)
        self.patch.start()
        self.conn = services.init_db(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        self.conn.close()
        self.patch.stop()
        self.tmp.cleanup()

    def upload(self, name, **kw):
        return services.process_upload(self.conn, (FIX / name).read_bytes(), name, **kw)

    def fields(self, run_id, **overrides):
        f = {k: v["value"] for k, v in services.get_run(self.conn, run_id)["fields"].items()}
        f.update(overrides)
        return f

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_upload_persists_document_run_and_fields(self):
        r = self.upload("clean_notice.pdf", ground_truth=EXPECTED["clean_notice.pdf"]["expected"])
        self.assertEqual(r["status"], "success")
        self.assertEqual((self.count("documents"), self.count("extracted_fields")), (1, 9))
        tasks = [x[0] for x in self.conn.execute("SELECT task FROM ai_runs ORDER BY ai_run_id")]
        self.assertEqual(tasks, ["extraction", "category_suggestion"])
        self.assertEqual(self.conn.execute("SELECT SUM(is_correct) FROM extracted_fields").fetchone()[0], 9)
        self.assertEqual(self.count("cases"), 0, "nothing becomes a case without human validation")

    def test_case_requires_explicit_validation(self):
        r = self.upload("clean_notice.pdf")
        with self.assertRaises(services.ServiceError) as ctx:
            services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), validated=False)
        self.assertEqual(ctx.exception.code, "VALIDATION_REQUIRED")
        self.assertEqual(self.count("cases"), 0)

    def test_required_fields_enforced(self):
        r = self.upload("clean_notice.pdf")
        with self.assertRaises(services.ServiceError) as ctx:
            services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"], client_name=""), True)
        self.assertEqual(ctx.exception.code, "MISSING_REQUIRED")

    def test_create_case_links_everything(self):
        r = self.upload("clean_notice.pdf")
        out = services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), True, "reviewer_x", "k1")
        case = self.conn.execute("SELECT * FROM cases").fetchone()
        self.assertEqual((out["status"], case["human_review_status"], case["status"]), ("created", "Approved", "Open"))
        self.assertEqual(self.conn.execute("SELECT case_id FROM documents").fetchone()[0], out["case_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM ai_runs WHERE case_id IS NULL").fetchone()[0], 0)
        self.assertEqual(self.count("human_reviews"), 1)
        events = [e[0] for e in self.conn.execute("SELECT event_type FROM audit_events ORDER BY event_id")]
        self.assertEqual(events[-2:], ["human_review_submitted", "case_created"])

    def test_missing_information_case_awaits_information(self):
        r = self.upload("missing_fields.pdf")
        out = services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), True, idempotency_key="m")
        case = self.conn.execute("SELECT status, intake_status, missing_fields FROM cases WHERE case_id = ?",
                                 (out["case_id"],)).fetchone()
        self.assertEqual((case["status"], case["intake_status"]), ("Awaiting information", "Missing Information"))
        self.assertEqual(set(json.loads(case["missing_fields"])), {"jurisdiction", "amounts"})

    def test_post_creation_edit_is_a_review(self):
        r = self.upload("clean_notice.pdf")
        out = services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), True, idempotency_key="e")
        services.update_case(self.conn, out["case_id"], {"category": "Contract dispute"}, "reviewer_y")
        self.assertEqual(self.conn.execute("SELECT category FROM cases").fetchone()[0], "Contract dispute")
        row = self.conn.execute("SELECT review_type, fields_corrected, category_changed FROM human_reviews"
                                " ORDER BY review_id DESC").fetchone()
        self.assertEqual(tuple(row), ("post_creation_edit", 1, 1))

    def test_summary_and_assistant_runs_recorded_without_question_text(self):
        r = self.upload("clean_notice.pdf")
        cid = services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), True,
                                   idempotency_key="s")["case_id"]
        s = services.summarise_case(self.conn, cid)
        self.assertEqual(s["status"], "success")
        self.assertTrue(self.conn.execute("SELECT summary FROM cases").fetchone()[0])
        question = "Which information is still missing? SECRET-QUESTION-MARKER"
        services.ask_case(self.conn, cid, question)
        tasks = [x[0] for x in self.conn.execute("SELECT task FROM ai_runs WHERE case_id = ?", (cid,))]
        self.assertIn("summarisation", tasks)
        self.assertIn("assistant", tasks)
        dump = "\n".join(self.conn.iterdump())
        self.assertNotIn("SECRET-QUESTION-MARKER", dump)

    def test_failed_run_is_recorded_and_not_reviewable(self):
        r = self.upload("clean_notice.pdf", simulate={"extract": {"mock-primary": "PROVIDER_ERROR",
                                                                 "mock-fallback": "PROVIDER_TIMEOUT"}})
        self.assertEqual(r["status"], "error")
        row = self.conn.execute("SELECT status, error_stage, error_code, fallback_used FROM ai_runs").fetchone()
        self.assertEqual(tuple(row), ("error", "ai_provider", "AI_UNAVAILABLE", 1))
        with self.assertRaises(services.ServiceError) as ctx:
            services.create_case(self.conn, r["ai_run_id"], {}, True)
        self.assertEqual(ctx.exception.code, "RUN_NOT_REVIEWABLE")

    def test_rejected_upload_starts_no_ai_run(self):
        r = self.upload("invalid_file.pdf")
        self.assertEqual(r["status"], "rejected")
        self.assertEqual(self.count("ai_runs"), 0)
        self.assertEqual(self.conn.execute("SELECT ingestion_status, rejection_code FROM documents").fetchone()[:],
                         ("rejected", "UNSUPPORTED_FORMAT"))

    def test_no_document_text_in_database_or_log(self):
        """Data minimisation: the narrative of the document is never persisted."""
        from ai.ingestion import ingest
        content = (FIX / "clean_notice.pdf").read_bytes()
        narrative = [ln for ln in ingest(content, "x.pdf").text.splitlines() if len(ln) > 60][0]
        r = self.upload("clean_notice.pdf")
        services.create_case(self.conn, r["ai_run_id"], self.fields(r["ai_run_id"]), True, idempotency_key="p")
        dump = "\n".join(self.conn.iterdump())
        self.assertNotIn(narrative, dump)
        log = self.log.read_text(encoding="utf-8")
        self.assertNotIn(narrative, log)
        self.assertNotIn(EXPECTED["clean_notice.pdf"]["expected"]["client_name"], log)

    def test_schema_constraints(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO documents (filename, byte_size, sha256, ingestion_status, uploaded_by,"
                              " uploaded_at) VALUES ('x', 1, 'h', 'rejected', 'u', '2026-01-01')")  # no rejection code
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO test_runs (run_label, code_version, trigger, started_at, finished_at,"
                              " tests_total, tests_passed, tests_failed) VALUES ('r','v','ci','b','a',3,1,1)")


if __name__ == "__main__":
    unittest.main()
