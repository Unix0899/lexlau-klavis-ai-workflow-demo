"""Build the synthetic dataset by running the REAL workflow on synthetic documents.

    python scripts/build_dataset.py

1. generate ~260 fictional intakes (PDF / DOCX / PNG / JPG, 8 document variants) + ground truth
2. replay six months of activity (Jan-Jun 2026) through app/backend/services.py:
   upload -> AI extraction (with fallback) -> simulated human review -> case creation,
   retries, duplicate submissions, supporting documents, summaries, assistant questions
3. replay the test-run history: the scenario suite is really executed, with the
   synthetic bugs switched on until their (synthetic) fix date
4. export data/synthetic_cases.csv, synthetic_ai_runs.csv, synthetic_test_results.csv

What is simulated, and flagged as such in the data:
  * the human reviewer (human_reviews.is_simulated = 1): corrects each field to the ground truth
  * provider latency (ai_runs.latency_is_simulated = 1): the mock answers in milliseconds,
    so a latency model per format is used for the extraction and category runs
  * provider outages: injected with MockAIProvider's failure switch at a fixed rate
  * timestamps (a fixed synthetic timeline)
Everything else (text extraction, field extraction, confidence, missing-field and
conflict detection, duplicate prevention, accuracy against ground truth, test results)
is computed by the code.

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
"""
import csv
import heapq
import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ai import bug_replay  # noqa: E402
from ai.config import DISCLOSURE, SCORED_FIELDS  # noqa: E402
from app.backend import services  # noqa: E402
from synthetic_documents import make_case, render  # noqa: E402
from tests.e2e import scenarios  # noqa: E402

SEED = 20260924
N_INTAKES = 260
START, END = datetime(2026, 1, 5, 8, 30), datetime(2026, 6, 26, 18, 0)
DOCS_DIR = ROOT / "data" / "synthetic_documents"
DB_PATH = ROOT / "database" / "klavis_ai_demo.sqlite"

# Synthetic bug windows in the activity timeline (the fixes are replayed in the test history)
BUG_WINDOWS = {"docx_routing": datetime(2026, 2, 16, 9, 0),
               "category_substring": datetime(2026, 3, 9, 9, 0)}

VARIANTS = [  # (variant, formats, weight)
    ("clean", ["pdf"], 22), ("clean", ["docx"], 20), ("clean", ["png", "png", "jpg"], 12),
    ("degraded", ["pdf"], 9), ("degraded", ["jpg", "jpg", "png"], 9), ("multipage", ["pdf"], 10),
    ("missing_fields", ["pdf", "docx", "png"], 10), ("contradictory", ["pdf", "docx"], 8),
]
UPLOADERS = [f"user_{i:02d}" for i in range(1, 7)]
REVIEWERS = [f"reviewer_{i:02d}" for i in range(1, 5)]
QUESTIONS = ["What parties were identified?", "What important dates were detected?",
             "Which information is still missing?", "Summarise this case.", "What amounts are claimed?"]

SAMPLES = [  # curated examples offered on the "New Case" page (copied from the test fixtures)
    ("clean_notice.pdf", "01_clean_formal_notice.pdf"),
    ("clean_letter.docx", "02_employment_letter.docx"),
    ("clean_scan.png", "03_clean_scanned_contract_letter.png"),
    ("degraded_photo.jpg", "04_degraded_phone_photo.jpg"),
    ("missing_fields.pdf", "05_missing_fields_notice.pdf"),
    ("multiple_dates.docx", "06_multiple_dates_summons.docx"),
    ("multipage_contract.pdf", "07_multipage_contract_dispute.pdf"),
    ("contradictory.docx", "08_contradictory_amounts.docx"),
    ("cardboard_commercial.pdf", "09_cardboard_invoice_dispute.pdf"),
]


def business_time(rng):
    while True:
        t = START + timedelta(seconds=rng.randrange(int((END - START).total_seconds())))
        if t.weekday() < 5 and 8 <= t.hour < 18:
            return t


def replay_flags(t):
    return tuple(flag for flag, fixed in BUG_WINDOWS.items() if t < fixed)


def extraction_latency(rng, fmt, variant, pages, failure):
    base = {"pdf": 850 + 380 * (pages - 1), "docx": 620, "png": 2300, "jpg": 2500}[fmt]
    if variant == "degraded":
        base += 900
    ms = base * rng.uniform(0.8, 1.35)
    if failure:  # time lost on the primary before falling back
        codes = failure.get("mock-primary")
        ms += {"PROVIDER_TIMEOUT": 6000, "PROVIDER_ERROR": 450, "INVALID_OUTPUT": 1300}.get(codes, 0)
        if "mock-fallback" in failure:
            ms += 400
    return round(ms, 1)


def reset_outputs():
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)
    for p in (DB_PATH, ROOT / "logs" / "dataset_build.log"):
        if p.exists():
            p.unlink()


def main():
    rng = random.Random(SEED)
    reset_outputs()
    conn = services.init_db(DB_PATH)
    ground_truth = {"disclosure": DISCLOSURE, "seed": SEED,
                    "comparison_rules": "see ai/evaluation.py and docs/AI_QUALITY_FRAMEWORK.md",
                    "documents": {}, "samples": {}}

    # ---------------------------------------------------------------- curated samples
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "expected.json").read_text(encoding="utf-8"))["fixtures"]
    (DOCS_DIR / "samples").mkdir()
    for src, dst in SAMPLES:
        shutil.copyfile(ROOT / "tests" / "fixtures" / src, DOCS_DIR / "samples" / dst)
        ground_truth["samples"][f"samples/{dst}"] = fixtures[src]

    # ---------------------------------------------------------------- event queue
    queue, counter = [], [0]

    def push(t, kind, **payload):
        counter[0] += 1
        heapq.heappush(queue, (t, counter[0], kind, payload))

    intakes = []
    for i in range(1, N_INTAKES + 1):
        variant, formats, _ = rng.choices(VARIANTS, weights=[v[2] for v in VARIANTS])[0]
        intakes.append((business_time(rng), variant, rng.choice(formats)))
    intakes.sort()
    for seq, (t, variant, fmt) in enumerate(intakes, 1):
        push(t, "intake", seq=seq, variant=variant, fmt=fmt)
    for k in range(8):
        push(business_time(rng), "bad_upload", bad=["invalid", "oversized", "executable"][k % 3], k=k)

    files = {}          # seq -> (path, bytes, truth, variant, fmt, pages)
    facts = {}          # seq -> fictional case facts
    case_of = {}        # seq -> case_id
    stats = {"intakes": 0, "cases": 0, "duplicates_blocked": 0, "retries": 0, "abandoned": 0,
             "supporting": 0, "double_clicks": 0}

    def upload(seq, t, actor, retry_of=None, role="primary", case_id=None, doc=None, force_ok=False):
        path, content, truth, variant, fmt, pages = doc or files[seq]
        r = rng.random()
        failure = None
        if not force_ok:
            if r < 0.015:
                failure = {"mock-primary": "PROVIDER_ERROR", "mock-fallback": "PROVIDER_TIMEOUT"}
            elif r < 0.085:
                failure = {"mock-primary": rng.choice(["PROVIDER_TIMEOUT", "PROVIDER_TIMEOUT",
                                                       "PROVIDER_ERROR", "INVALID_OUTPUT"])}
        cat_failure = {"mock-primary": "PROVIDER_TIMEOUT"} if rng.random() < 0.03 else None
        with bug_replay.bug_replay(*replay_flags(t)):
            return services.process_upload(
                conn, content, path.name, actor=actor, now=t, sample_variant=variant,
                storage_path=path.relative_to(ROOT).as_posix(),
                simulate={"extract": failure, "suggest_category": cat_failure},
                ground_truth=truth, latency_ms=extraction_latency(rng, fmt, variant, pages, failure),
                category_latency_ms=round(rng.uniform(180, 420) + (6000 if cat_failure else 0), 1),
                retry_of=retry_of, document_role=role, case_id=case_id, write_log=False)

    def review_and_create(seq, res, t, reviewer, duplicate=False):
        truth = files[seq][2]
        fields = {f: truth[f] for f in SCORED_FIELDS}
        n_diff = sum(1 for f in SCORED_FIELDS if f in res["result"] and
                     services.canonical(f, res["result"][f]) != services.canonical(f, truth[f]))
        seconds = int(35 + 22 * n_diff + 12 * len(res["result"]["missing_fields"]) + rng.uniform(0, 40))
        done = t + timedelta(seconds=seconds + rng.randrange(60, 1800))
        key = f"intake-{seq}-{'dup' if duplicate else 'main'}"
        try:
            out = services.create_case(conn, res["ai_run_id"], fields, True, reviewer, idempotency_key=key,
                                       now=done, review_seconds=seconds, is_simulated=True, write_log=False)
        except services.ServiceError as exc:
            if exc.code == "DUPLICATE_CASE":
                stats["duplicates_blocked"] += 1
                return None
            raise
        if rng.random() < 0.04:  # double click: the same submission arrives twice
            services.create_case(conn, res["ai_run_id"], fields, True, reviewer, idempotency_key=key,
                                 now=done + timedelta(seconds=1), is_simulated=True, write_log=False)
            stats["double_clicks"] += 1
        return out["case_id"], done

    while queue:
        t, _, kind, p = heapq.heappop(queue)
        if kind == "bad_upload":
            content = {"invalid": bytes(rng.randrange(256) for _ in range(3000)),
                       "oversized": b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024 + 10),
                       "executable": b"MZ\x90\x00" + bytes(2000)}[p["bad"]]
            name = {"invalid": "scan_export.pdf", "oversized": "full_archive.pdf",
                    "executable": "contract_final.docx"}[p["bad"]]
            services.process_upload(conn, content, name, actor=rng.choice(UPLOADERS), now=t,
                                    sample_variant="oversized" if p["bad"] == "oversized" else "invalid",
                                    write_log=False)
            continue

        if kind == "intake":
            seq = p["seq"]
            case = make_case(rng, seq)
            content, truth, pages = render(case, p["variant"], p["fmt"], rng)
            folder = DOCS_DIR / p["variant"]
            folder.mkdir(exist_ok=True)
            path = folder / f"DOC-{seq:04d}_{case['document_type'].lower().replace(' ', '_')}.{p['fmt']}"
            path.write_bytes(content)
            files[seq] = (path, content, truth, p["variant"], p["fmt"], pages)
            ground_truth["documents"][path.relative_to(DOCS_DIR).as_posix()] = {
                "intake": seq, "variant": p["variant"], "format": p["fmt"], "pages": pages,
                "role": "primary", "expected": truth}
            stats["intakes"] += 1
            res = upload(seq, t, rng.choice(UPLOADERS))
            facts[seq] = case
        elif kind == "retry":
            seq = p["seq"]
            stats["retries"] += 1
            res = upload(seq, t, p["actor"], retry_of=p["run_id"], force_ok=p.get("force_ok", False))
        elif kind == "duplicate":
            seq = p["seq"]
            res = upload(seq, t, rng.choice(UPLOADERS))
            if res["status"] == "success":
                review_and_create(seq, res, t, rng.choice(REVIEWERS), duplicate=True)
            continue
        elif kind == "supporting":
            seq, case = p["seq"], p["case"]
            variant = rng.choice(["clean", "clean", "degraded"])
            fmt = rng.choice(["pdf", "docx", "jpg"]) if variant == "clean" else rng.choice(["pdf", "jpg"])
            sup = dict(case, document_type=rng.choice(["Formal notice", "Invoice dispute letter", "Court summons"]))
            content, truth, pages = render(sup, variant, fmt, rng)
            path = DOCS_DIR / "supporting" / f"DOC-{seq:04d}-S_{sup['document_type'].lower().replace(' ', '_')}.{fmt}"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)
            ground_truth["documents"][path.relative_to(DOCS_DIR).as_posix()] = {
                "intake": seq, "variant": variant, "format": fmt, "pages": pages, "role": "supporting",
                "expected": truth}
            upload(seq, t, rng.choice(UPLOADERS), role="supporting", case_id=p["case_id"],
                   doc=(path, content, truth, variant, fmt, pages))
            stats["supporting"] += 1
            continue
        elif kind == "summary":
            services.summarise_case(conn, p["case_id"], now=t, write_log=False)
            continue
        elif kind == "ask":
            services.ask_case(conn, p["case_id"], p["question"], now=t, write_log=False)
            continue
        elif kind == "close":
            services.update_case(conn, p["case_id"], {"status": "Closed"}, rng.choice(REVIEWERS), now=t,
                                 write_log=False)
            continue

        # ---- after an intake or a retry
        if res["status"] == "error":
            seq = p["seq"]
            if res.get("error_stage") == "text_extraction" and "docx_routing" in replay_flags(t):
                when = max(t, BUG_WINDOWS["docx_routing"]) + timedelta(hours=rng.randrange(2, 72))
                push(when, "retry", seq=seq, run_id=res["ai_run_id"], actor=rng.choice(UPLOADERS))
            elif rng.random() < 0.85 and p.get("attempt", 0) < 2:
                push(t + timedelta(minutes=rng.randrange(10, 180)), "retry", seq=seq,
                     run_id=res["ai_run_id"], actor=rng.choice(UPLOADERS), force_ok=True)
            else:
                stats["abandoned"] += 1
            continue
        if res["status"] != "success":
            continue
        seq = p["seq"]
        created = review_and_create(seq, res, t, rng.choice(REVIEWERS))
        if not created:
            continue
        case_id, done = created
        case_of[seq] = case_id
        stats["cases"] += 1
        case_facts = facts[seq]
        if rng.random() < 0.05:
            push(done + timedelta(days=rng.randrange(2, 25)), "duplicate", seq=seq)
        if rng.random() < 0.18:
            push(done + timedelta(days=rng.randrange(1, 12), hours=rng.randrange(0, 5)), "supporting",
                 seq=seq, case=case_facts, case_id=case_id)
        if rng.random() < 0.55:
            push(done + timedelta(minutes=rng.randrange(2, 90)), "summary", case_id=case_id)
        if rng.random() < 0.2:
            for qn in rng.sample(QUESTIONS, rng.choice([1, 2])):
                push(done + timedelta(minutes=rng.randrange(5, 240)), "ask", case_id=case_id, question=qn)
        close_at = done + timedelta(days=rng.randrange(20, 70))
        if close_at < END and rng.random() < 0.45:
            push(close_at, "close", case_id=case_id)

    # ---------------------------------------------------------------- test-run history
    history = [
        ("v0.4 baseline - bug replay (5 synthetic bugs)", "0.4.0", set(bug_replay.BUGS), datetime(2026, 2, 12, 16, 5)),
        ("fix/docx-content-routing", "0.4.1", {"category_substring", "missing_as_zero", "fallback_mislabel",
                                               "duplicate_no_idempotency"}, datetime(2026, 2, 16, 8, 40)),
        ("fix/category-word-boundary", "0.4.2", {"missing_as_zero", "fallback_mislabel",
                                                 "duplicate_no_idempotency"}, datetime(2026, 3, 9, 8, 35)),
        ("fix/missing-field-null", "0.5.0", {"fallback_mislabel", "duplicate_no_idempotency"},
         datetime(2026, 3, 30, 11, 20)),
        ("merge feature/assistant-intents (regression caught)", "0.6.0-rc1",
         {"docx_routing", "fallback_mislabel", "duplicate_no_idempotency"}, datetime(2026, 4, 14, 15, 10)),
        ("revert routing + fix/fallback-provider-label", "0.6.0", {"duplicate_no_idempotency"},
         datetime(2026, 4, 20, 10, 0)),
        ("fix/idempotent-case-creation", "0.7.0", set(), datetime(2026, 5, 12, 14, 30)),
        ("release candidate v1.0 - full regression", "1.0.0", set(), datetime(2026, 6, 26, 17, 0)),
    ]
    for label, version, flags, t in history:
        results = scenarios.run_suite(tuple(sorted(flags)))
        total_ms = sum(r["duration_ms"] for r in results)
        run_id, passed = scenarios.record_run(conn, results, label, version, "ci", t.isoformat(timespec="seconds"),
                                              (t + timedelta(milliseconds=total_ms)).isoformat(timespec="seconds"),
                                              flags)
        services.audit(conn, "test_run_completed", "ci", t, False, entity_type="test_run", entity_id=run_id,
                       tests_passed=passed, tests_failed=len(results) - passed,
                       bug_replay=",".join(sorted(flags)) or "none")
        conn.commit()
        print(f"  test run {run_id}: {label:55} {passed}/{len(results)}")

    (ROOT / "data" / "ground_truth.json").write_text(json.dumps(ground_truth, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")
    export_csvs(conn)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ("cases", "documents", "ai_runs", "extracted_fields", "human_reviews", "ai_feedback",
               "test_runs", "test_results", "audit_events")}
    print("  stats:", stats)
    print("  rows:", counts)
    conn.execute("VACUUM")
    conn.close()


def export_csvs(conn):
    def dump(path, sql):
        cur = conn.execute(sql)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur.fetchall())

    data = ROOT / "data"
    dump(data / "synthetic_cases.csv",
         "SELECT c.case_id, c.case_reference, c.title, c.client_name, c.opposing_party, c.category, c.jurisdiction,"
         " c.document_type, c.status, c.intake_status, c.ai_confidence, c.human_review_status,"
         " c.important_dates, c.amounts, c.missing_fields, d.filename AS source_document, d.detected_format,"
         " d.sample_variant, c.created_by, c.created_at, c.updated_at FROM cases c"
         " JOIN documents d ON d.document_id = c.source_document_id ORDER BY c.case_id")
    dump(data / "synthetic_ai_runs.csv",
         "SELECT r.ai_run_id, r.document_id, r.case_id, r.task, d.detected_format, d.sample_variant,"
         " d.document_role, r.provider_requested, r.provider_used, r.fallback_used, r.fallback_reason, r.status,"
         " r.error_stage, r.error_code, r.confidence_score, r.intake_status, r.missing_count, r.conflict_count,"
         " r.processing_ms, r.latency_is_simulated, r.retry_of_run_id, r.bug_replay, r.started_at"
         " FROM ai_runs r JOIN documents d USING (document_id) ORDER BY r.ai_run_id")
    dump(data / "synthetic_test_results.csv",
         "SELECT t.test_run_id, t.run_label, t.code_version, t.bug_replay, t.started_at, r.scenario_code,"
         " r.scenario_name, r.document_format, r.expected, r.observed, r.status, r.failure_category,"
         " r.is_regression, r.duration_ms FROM test_results r JOIN test_runs t USING (test_run_id)"
         " ORDER BY t.test_run_id, r.scenario_code")


if __name__ == "__main__":
    main()
