"""TEST 001 - TEST 014 must all pass, and each synthetic bug must be caught by the suite."""
import unittest

from tests.e2e.scenarios import SCENARIOS, run_suite

# which scenario is expected to catch which replayed bug
CATCHES = {
    "docx_routing": {"TEST 002", "TEST 013", "TEST 014"},
    "category_substring": {"TEST 014"},
    "duplicate_no_idempotency": {"TEST 009"},
    "fallback_mislabel": {"TEST 007"},
    "missing_as_zero": {"TEST 005"},
}


class ScenarioSuite(unittest.TestCase):
    def test_all_scenarios_pass(self):
        results = run_suite()
        self.assertEqual(len(results), len(SCENARIOS))
        for r in results:
            with self.subTest(scenario=r["scenario_code"]):
                self.assertEqual(r["status"], "PASS", r["observed"])

    def test_each_synthetic_bug_is_detected(self):
        for flag, expected_failures in CATCHES.items():
            with self.subTest(bug=flag):
                failed = {r["scenario_code"] for r in run_suite((flag,)) if r["status"] == "FAIL"}
                self.assertTrue(expected_failures <= failed, f"{flag}: failed={sorted(failed)}")


if __name__ == "__main__":
    unittest.main()
