"""The published dataset: database integrity, volumes, views, ground truth, CSV exports."""
import csv
import json
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "database" / "klavis_ai_demo.sqlite"
VIEWS = ["vw_ai_quality_summary", "vw_document_type_performance", "vw_field_accuracy",
         "vw_test_run_summary", "vw_human_review_metrics", "vw_error_analysis"]


class ReferenceDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def one(self, sql):
        return self.conn.execute(sql).fetchone()[0]

    def test_integrity_and_foreign_keys(self):
        self.assertEqual(self.one("PRAGMA integrity_check"), "ok")
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_volumes_within_spec(self):
        self.assertTrue(100 <= self.one("SELECT COUNT(*) FROM cases") <= 300)
        self.assertTrue(300 <= self.one("SELECT COUNT(*) FROM ai_runs") <= 1000)
        self.assertEqual(self.one("SELECT COUNT(DISTINCT scenario_code) FROM test_results"), 14)

    def test_all_views_return_rows(self):
        for v in VIEWS:
            with self.subTest(view=v):
                self.assertGreater(self.one(f"SELECT COUNT(*) FROM {v}"), 0)

    def test_no_duplicate_case_reference(self):
        self.assertEqual(self.one("SELECT COUNT(*) - COUNT(DISTINCT reference_key) FROM cases"), 0)

    def test_every_case_was_human_validated(self):
        self.assertEqual(self.one("SELECT COUNT(*) FROM cases c WHERE NOT EXISTS (SELECT 1 FROM human_reviews h"
                                  " WHERE h.case_id = c.case_id AND h.review_type = 'intake_validation')"), 0)

    def test_latest_test_run_is_green(self):
        self.assertEqual(self.one("SELECT tests_failed FROM test_runs ORDER BY test_run_id DESC LIMIT 1"), 0)

    def test_simulated_parts_are_flagged(self):
        self.assertEqual(self.one("SELECT MIN(is_simulated) FROM human_reviews WHERE review_type = 'intake_validation'"), 1)
        self.assertEqual(self.one("SELECT MIN(latency_is_simulated) FROM ai_runs WHERE task = 'extraction'"), 1)

    def test_ground_truth_matches_documents_on_disk(self):
        gt = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
        self.assertIn("Synthetic demonstration data", gt["disclosure"])
        docs = ROOT / "data" / "synthetic_documents"
        for rel in list(gt["documents"]) + list(gt["samples"]):
            self.assertTrue((docs / rel).is_file(), rel)
        variants = {d["variant"] for d in gt["documents"].values()}
        self.assertTrue({"clean", "degraded", "multipage", "missing_fields", "contradictory"} <= variants)
        formats = {d["format"] for d in gt["documents"].values()}
        self.assertEqual(formats, {"pdf", "docx", "png", "jpg"})

    def test_csv_exports_match_database(self):
        for name, table in (("synthetic_cases.csv", "cases"), ("synthetic_ai_runs.csv", "ai_runs"),
                            ("synthetic_test_results.csv", "test_results")):
            with self.subTest(csv=name), open(ROOT / "data" / name, encoding="utf-8") as fh:
                rows = sum(1 for _ in csv.reader(fh)) - 1
                self.assertEqual(rows, self.one(f"SELECT COUNT(*) FROM {table}"))

    def test_audit_has_no_document_text(self):
        biggest = self.one("SELECT MAX(LENGTH(details)) FROM audit_events")
        self.assertLess(biggest, 400)
        self.assertEqual(self.one("SELECT COUNT(*) FROM audit_events WHERE details LIKE '%Our client%'"), 0)


if __name__ == "__main__":
    unittest.main()
