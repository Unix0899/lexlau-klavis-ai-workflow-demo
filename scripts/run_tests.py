"""Run the whole test suite (unit + integration + e2e) and write docs/TEST_REPORT.md.

    python scripts/run_tests.py
"""
import io
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records = []

    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def _add(self, test, status):
        self.records.append((test.id(), status, round((time.perf_counter() - self._t0) * 1000)))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL")

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._add(subtest, "FAIL")


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Recorder)
    started = time.perf_counter()
    result = runner.run(suite)
    elapsed = time.perf_counter() - started
    print(stream.getvalue()[-3000:])

    by_level = {}
    for test_id, status, _ in result.records:
        level = test_id.split(".")[1] if test_id.startswith("tests.") else "other"
        by_level.setdefault(level, [0, 0])
        by_level[level][0 if status == "PASS" else 1] += 1
    lines = ["# Test report", "",
             "> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.",
             "", f"Run on {datetime.now():%d/%m/%Y %H:%M} with `python scripts/run_tests.py` "
             f"(Python {sys.version.split()[0]}, standard `unittest`, {elapsed:.1f} s).", "",
             "| Level | Passed | Failed |", "|---|---:|---:|"]
    for level, (ok, ko) in sorted(by_level.items()):
        lines.append(f"| {level} | {ok} | {ko} |")
    total_ok = sum(v[0] for v in by_level.values())
    total_ko = sum(v[1] for v in by_level.values())
    lines += [f"| **Total** | **{total_ok}** | **{total_ko}** |", "",
              "TEST 001 - TEST 014 are executed inside `tests/e2e/test_scenarios.py` (all 14 as sub-tests, "
              "plus one check per replayed synthetic bug).", "", "## Tests", "",
              "| Test | Result | ms |", "|---|---|---:|"]
    for test_id, status, ms in result.records:
        lines.append(f"| `{test_id.replace('tests.', '', 1)}` | {status} | {ms} |")
    (ROOT / "docs" / "TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{total_ok} passed, {total_ko} failed -> docs/TEST_REPORT.md")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
