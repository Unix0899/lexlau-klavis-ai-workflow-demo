"""TEST 001 - TEST 014: the AI workflow scenario suite.

Each scenario runs the real workflow (ingestion -> AI chain -> checks -> database ->
human validation -> case) on a fresh temporary database and returns
(passed: bool, observed: str). The same functions are used by:

  * tests/e2e/test_scenarios.py      (unittest, must be 14/14 with no bug replay)
  * scripts/build_dataset.py         (test-run history, replaying the synthetic bugs)
  * the "Run test suite" button      (AI Tests page of the demo app)
"""
import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from ai import bug_replay
from ai.config import MAX_UPLOAD_BYTES, SCORED_FIELDS
from ai.evaluation import canonical, is_correct
from ai.registry import build_chain
from app.backend import services

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _expected():
    return json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))["fixtures"]


@contextmanager
def fresh_db():
    tmp = tempfile.TemporaryDirectory()
    conn = services.init_db(Path(tmp.name) / "scenario.sqlite")
    try:
        yield conn
    finally:
        conn.close()
        tmp.cleanup()


def _upload(conn, name, **kw):
    return services.process_upload(conn, (FIXTURES / name).read_bytes(), name, actor="qa_runner",
                                   write_log=False, **kw)


def _wrong_fields(result, name):
    exp = _expected()[name]["expected"]
    return [f for f in SCORED_FIELDS if not is_correct(f, result.get(f), exp[f])]


def _validated_fields(conn, run_id, **overrides):
    draft = services.get_run(conn, run_id)
    fields = {k: v["value"] for k, v in draft["fields"].items()}
    fields.update(overrides)
    return fields


# ------------------------------------------------------------------ scenarios
def t001_clean_pdf(conn):
    r = _upload(conn, "clean_notice.pdf")
    if r["status"] != "success":
        return False, f"status={r['status']} error={r.get('error_code')}"
    wrong = _wrong_fields(r["result"], "clean_notice.pdf")
    missing = r["result"]["missing_fields"]
    return (not wrong and not missing,
            f"{len(SCORED_FIELDS) - len(wrong)}/{len(SCORED_FIELDS)} fields correct; missing={missing}")


def t002_docx(conn):
    r = _upload(conn, "clean_letter.docx")
    if r["status"] != "success":
        return False, f"status={r['status']} error={r.get('error_code')} stage={r.get('error_stage')}"
    wrong = _wrong_fields(r["result"], "clean_letter.docx")
    return (r["ingestion"]["format"] == "docx" and not wrong,
            f"format={r['ingestion']['format']}; {len(SCORED_FIELDS) - len(wrong)}/{len(SCORED_FIELDS)} fields correct")


def t003_clean_image(conn):
    r = _upload(conn, "clean_scan.png")
    if r["status"] != "success":
        return False, f"status={r['status']} error={r.get('error_code')}"
    wrong = _wrong_fields(r["result"], "clean_scan.png")
    return (not wrong and r["result"]["case_status"] == "Complete",
            f"image text layer read; {len(SCORED_FIELDS) - len(wrong)}/{len(SCORED_FIELDS)} fields correct")


def t004_degraded_image(conn):
    clean = _upload(conn, "clean_scan.png")
    r = _upload(conn, "degraded_photo.jpg")
    if r["status"] != "success":
        return False, f"crash or error: status={r['status']} error={r.get('error_code')}"
    c_clean, c_deg = clean["result"]["confidence_score"], r["result"]["confidence_score"]
    ok = c_deg < c_clean and r["result"]["case_status"] != "Complete"
    return ok, f"no crash; confidence {c_deg} < clean {c_clean}; status={r['result']['case_status']}"


def t005_missing_field(conn):
    r = _upload(conn, "missing_fields.pdf")
    if r["status"] != "success":
        return False, f"status={r['status']}"
    res = r["result"]
    zero_amount = any(a.get("value") == 0 for a in res["amounts"])
    ok = ({"jurisdiction", "amounts"} <= set(res["missing_fields"]) and res["jurisdiction"] is None
          and not zero_amount and res["case_status"] == "Missing Information")
    return ok, f"missing_fields={res['missing_fields']}; amounts={[a['value'] for a in res['amounts']]}"


def t006_multiple_dates(conn):
    r = _upload(conn, "multiple_dates.docx")
    if r["status"] != "success":
        return False, f"status={r['status']} error={r.get('error_code')}"
    exp = _expected()["multiple_dates.docx"]["expected"]["important_dates"]
    got = r["result"]["important_dates"]
    ok = canonical("important_dates", got) == canonical("important_dates", exp)
    return ok, "; ".join(f"{d['label']}={d['date']}" for d in got)


def t007_provider_failure(conn):
    r = _upload(conn, "clean_notice.pdf", simulate={"extract": {"mock-primary": "PROVIDER_TIMEOUT"}})
    if r["status"] != "success":
        return False, f"status={r['status']} error={r.get('error_code')}"
    row = conn.execute("SELECT provider_used, fallback_used, fallback_reason FROM ai_runs"
                       " WHERE ai_run_id = ?", (r["ai_run_id"],)).fetchone()
    ok = (row["provider_used"] == "mock-fallback" and row["fallback_used"] == 1
          and row["fallback_reason"] == "PROVIDER_TIMEOUT")
    return ok, (f"stored provider_used={row['provider_used']}, fallback_used={row['fallback_used']}, "
                f"reason={row['fallback_reason']}")


def t008_both_providers_fail(conn):
    r = _upload(conn, "clean_notice.pdf", simulate={"extract": {"mock-primary": "PROVIDER_ERROR",
                                                               "mock-fallback": "INVALID_OUTPUT"}})
    cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    ok = (r["status"] == "error" and r["error_code"] == "AI_UNAVAILABLE" and bool(r.get("message"))
          and cases == 0 and len(r.get("attempts", [])) == 2)
    return ok, f"status={r['status']} error_code={r.get('error_code')} attempts={len(r.get('attempts', []))} cases={cases}"


def t009_duplicate_submission(conn):
    r = _upload(conn, "clean_notice.pdf")
    fields = _validated_fields(conn, r["ai_run_id"])
    outcomes = []
    for _ in range(2):  # double click on "Create case"
        try:
            outcomes.append(services.create_case(conn, r["ai_run_id"], fields, True, "qa_reviewer",
                                                 idempotency_key="qa-key-1", write_log=False)["status"])
        except services.ServiceError as exc:
            outcomes.append(exc.code)
    r2 = _upload(conn, "clean_notice.pdf")  # same document uploaded again later
    try:
        outcomes.append(services.create_case(conn, r2["ai_run_id"], _validated_fields(conn, r2["ai_run_id"]),
                                             True, "qa_reviewer", idempotency_key="qa-key-2",
                                             write_log=False)["status"])
    except services.ServiceError as exc:
        outcomes.append(exc.code)
    cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    return cases == 1, f"cases created={cases}; submissions -> {outcomes}"


def t010_human_correction(conn):
    r = _upload(conn, "degraded_photo.jpg")
    if r["status"] != "success":
        return False, f"status={r['status']}"
    exp = _expected()["degraded_photo.jpg"]["expected"]
    fields = _validated_fields(conn, r["ai_run_id"], client_name=exp["client_name"],
                               case_reference=exp["case_reference"], case_title=exp["case_title"],
                               case_category="Contract dispute")
    created = services.create_case(conn, r["ai_run_id"], fields, True, "qa_reviewer",
                                   idempotency_key="qa-key-10", write_log=False)
    case = conn.execute("SELECT client_name, category, human_review_status FROM cases WHERE case_id = ?",
                        (created["case_id"],)).fetchone()
    row = conn.execute("SELECT final_value, was_corrected FROM extracted_fields WHERE ai_run_id = ?"
                       " AND field_name = 'case_category'", (r["ai_run_id"],)).fetchone()
    fb = conn.execute("SELECT COUNT(*) FROM ai_feedback WHERE ai_run_id = ?", (r["ai_run_id"],)).fetchone()[0]
    ok = (case["client_name"] == exp["client_name"] and case["category"] == "Contract dispute"
          and row["final_value"] == "Contract dispute" and row["was_corrected"] == 1
          and case["human_review_status"] == "Approved with corrections" and fb >= 1)
    return ok, (f"case.category={case['category']}; field final={row['final_value']} corrected={row['was_corrected']};"
                f" {created['fields_corrected']} corrections, {fb} feedback rows")


def t011_invalid_file(conn):
    codes = [_upload(conn, n).get("error_code") for n in ("invalid_file.pdf", "renamed_executable.docx")]
    runs = conn.execute("SELECT COUNT(*) FROM ai_runs").fetchone()[0]
    ok = codes == ["UNSUPPORTED_FORMAT", "UNSUPPORTED_FORMAT"] and runs == 0
    return ok, f"rejections={codes}; ai_runs started={runs}"


def t012_oversized_file(conn):
    content = b"%PDF-1.4\n" + b"0" * (MAX_UPLOAD_BYTES + 1)
    r = services.process_upload(conn, content, "oversized.pdf", actor="qa_runner", write_log=False)
    runs = conn.execute("SELECT COUNT(*) FROM ai_runs").fetchone()[0]
    ok = r["status"] == "rejected" and r["error_code"] == "FILE_TOO_LARGE" and runs == 0
    return ok, f"status={r['status']} error_code={r.get('error_code')}; ai_runs started={runs}"


def t013_mixed_formats(conn):
    results = {}
    for fmt in ("pdf", "docx", "png"):
        r = _upload(conn, f"mixed_same_case.{fmt}")
        results[fmt] = r["result"] if r["status"] == "success" else None
    if any(v is None for v in results.values()):
        return False, "failed formats: " + ", ".join(k for k, v in results.items() if v is None)
    diff = [f for f in SCORED_FIELDS
            if len({canonical(f, results[fmt].get(f)) for fmt in results}) > 1]
    return not diff, f"PDF / DOCX / PNG identical on {len(SCORED_FIELDS) - len(diff)}/{len(SCORED_FIELDS)} fields"


GOLDEN = ["clean_notice.pdf", "clean_letter.docx", "clean_scan.png", "multiple_dates.docx",
          "multipage_contract.pdf", "cardboard_commercial.pdf"]


def t014_regression(conn):
    failures = []
    for name in GOLDEN:
        r = _upload(conn, name)
        if r["status"] != "success":
            failures.append(f"{name}:{r.get('error_code')}")
            continue
        failures += [f"{name}:{f}" for f in _wrong_fields(r["result"], name)]
    return not failures, (f"{len(GOLDEN)} golden documents, all fields match" if not failures
                          else "diffs: " + ", ".join(failures))


SCENARIOS = [
    ("TEST 001", "Clean PDF", "pdf", "All required fields extracted", "extraction_accuracy", t001_clean_pdf),
    ("TEST 002", "DOCX", "docx", "Text correctly extracted", "document_routing", t002_docx),
    ("TEST 003", "Clean image", "png", "OCR / vision processing succeeds", "ocr_processing", t003_clean_image),
    ("TEST 004", "Degraded image", "jpg", "Lower confidence but no crash", "robustness", t004_degraded_image),
    ("TEST 005", "Missing field", "pdf", "Field appears in missing_fields (null, not 0)",
     "missing_field_handling", t005_missing_field),
    ("TEST 006", "Multiple dates", "docx", "Dates structured correctly (label + ISO)", "date_normalisation",
     t006_multiple_dates),
    ("TEST 007", "Provider failure", "pdf", "Fallback invoked and recorded", "provider_fallback",
     t007_provider_failure),
    ("TEST 008", "Both providers fail", "pdf", "Controlled error, nothing saved", "error_handling",
     t008_both_providers_fail),
    ("TEST 009", "Duplicate submission", "pdf", "No duplicate case created", "duplicate_prevention",
     t009_duplicate_submission),
    ("TEST 010", "Human correction", "jpg", "Corrected value persisted", "human_review_persistence",
     t010_human_correction),
    ("TEST 011", "Invalid file", "invalid", "Rejected safely, no AI run", "input_validation", t011_invalid_file),
    ("TEST 012", "Oversized file", "pdf", "Controlled rejection", "input_validation", t012_oversized_file),
    ("TEST 013", "Mixed document formats", "mixed", "PDF / DOCX / image processed consistently",
     "document_routing", t013_mixed_formats),
    ("TEST 014", "Regression suite", "mixed", "Previously working workflows remain functional",
     "regression", t014_regression),
]


def run_suite(replay=(), only=None):
    """Run every scenario (optionally with bug replay switches). Returns a list of result dicts."""
    results = []
    with bug_replay.bug_replay(*replay):
        for code, name, fmt, expected, category, fn in SCENARIOS:
            if only and code not in only:
                continue
            started = time.perf_counter()
            with fresh_db() as conn:
                try:
                    passed, observed = fn(conn)
                except Exception as exc:  # a crash is a failure, never an abort of the suite
                    passed, observed = False, f"crash: {type(exc).__name__}: {exc}"[:200]
            results.append({"scenario_code": code, "scenario_name": name, "document_format": fmt,
                            "expected": expected, "observed": observed,
                            "status": "PASS" if passed else "FAIL",
                            "failure_category": None if passed else category,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
    return results


def record_run(conn, results, run_label, code_version, trigger, started_at, finished_at, replay=()):
    previous = {r["scenario_code"]: r["status"] for r in conn.execute(
        "SELECT scenario_code, status FROM test_results WHERE test_run_id ="
        " (SELECT MAX(test_run_id) FROM test_runs)").fetchall()}
    passed = sum(r["status"] == "PASS" for r in results)
    cur = conn.execute(
        "INSERT INTO test_runs (run_label, code_version, bug_replay, trigger, started_at, finished_at,"
        " tests_total, tests_passed, tests_failed) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_label, code_version, ",".join(sorted(replay)) or None, trigger, started_at, finished_at,
         len(results), passed, len(results) - passed))
    run_id = cur.lastrowid
    for r in results:
        conn.execute(
            "INSERT INTO test_results (test_run_id, scenario_code, scenario_name, document_format, expected,"
            " observed, status, failure_category, is_regression, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, r["scenario_code"], r["scenario_name"], r["document_format"], r["expected"],
             r["observed"], r["status"], r["failure_category"],
             int(r["status"] == "FAIL" and previous.get(r["scenario_code"]) == "PASS"), r["duration_ms"]))
    conn.commit()
    return run_id, passed
