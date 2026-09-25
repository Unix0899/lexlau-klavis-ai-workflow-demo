"""Export the Power BI star schema (CSV) from the SQLite database.

    powerbi/data/DimDate.csv, DimDocumentType.csv, DimAIProvider.csv, DimTestScenario.csv,
    FactAIRuns.csv, FactFieldExtraction.csv, FactHumanReview.csv, FactTestResults.csv, FactAuditEvents.csv

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
No free text leaves the database: titles, names and document content are not exported.
"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "klavis_ai_demo.sqlite"
OUT = ROOT / "powerbi" / "data"

FIELD_LABELS = {"case_title": "Case title", "case_reference": "Case reference", "client_name": "Client",
                "opposing_party": "Opposing party", "document_type": "Document type",
                "jurisdiction": "Jurisdiction", "important_dates": "Dates", "amounts": "Amounts",
                "case_category": "Category"}
EVENT_GROUPS = {
    "file_rejected": "Input validation", "duplicate_case_blocked": "Duplicate prevention",
    "duplicate_submission_ignored": "Duplicate prevention", "human_review_submitted": "Human review",
    "case_updated": "Human review", "case_created": "Case lifecycle", "document_uploaded": "Document intake",
    "ai_extraction_completed": "AI processing", "ai_extraction_failed": "AI processing",
    "provider_fallback_used": "AI processing", "summary_generated": "AI assistance",
    "assistant_question": "AI assistance", "test_run_completed": "Testing",
}
VARIANT_ORDER = ["clean", "multipage", "degraded", "missing_fields", "contradictory", "upload"]


def date_key(col):
    return pd.to_datetime(col).dt.strftime("%Y%m%d").astype(int)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = lambda sql: pd.read_sql_query(sql, conn)  # noqa: E731

    # ------------------------------------------------------------------ dimensions
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range((date(2026, 7, 31) - date(2026, 1, 1)).days + 1)]
    dim_date = pd.DataFrame({"date": [d.isoformat() for d in days]})
    d = pd.to_datetime(dim_date["date"])
    dim_date["date_key"] = d.dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = d.dt.year
    dim_date["month"] = d.dt.month
    dim_date["month_name"] = d.dt.strftime("%b")
    dim_date["year_month"] = d.dt.strftime("%Y-%m")
    dim_date["week_start"] = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    dim_date["is_weekday"] = (d.dt.weekday < 5).astype(int)

    docs = q("SELECT DISTINCT detected_format, sample_variant FROM documents WHERE detected_format IS NOT NULL")
    docs["file_family"] = docs.detected_format.map({"pdf": "PDF", "docx": "DOCX", "png": "Image", "jpg": "Image"})
    docs["variant_order"] = docs.sample_variant.map({v: i for i, v in enumerate(VARIANT_ORDER)}).fillna(9)
    docs["family_order"] = docs.file_family.map({"PDF": 1, "DOCX": 2, "Image": 3})
    docs = docs.sort_values(["family_order", "detected_format", "variant_order"]).reset_index(drop=True)
    docs["document_type_id"] = docs.index + 1
    docs["document_type"] = [f"{fam} {fmt.upper()} - {var.replace('_', ' ')}" if fam == "Image"
                             else f"{fam} - {var.replace('_', ' ')}"
                             for fam, fmt, var in zip(docs.file_family, docs.detected_format, docs.sample_variant)]
    dim_doc = docs[["document_type_id", "document_type", "file_family", "family_order", "detected_format",
                    "sample_variant", "variant_order"]].astype({"variant_order": int})
    doc_key = {(r.detected_format, r.sample_variant): r.document_type_id for r in dim_doc.itertuples()}

    dim_provider = pd.DataFrame([
        (1, "mock-primary", "Primary", 0, "Deterministic local engine (default)"),
        (2, "mock-fallback", "Fallback", 0, "Simpler local backup engine"),
        (3, "none (failed)", "None", 0, "No provider produced a valid output"),
    ], columns=["provider_id", "provider_name", "provider_role", "is_external", "description"])
    prov_key = {"mock-primary": 1, "mock-fallback": 2, None: 3}

    scen = q("SELECT scenario_code, scenario_name, document_format, expected FROM test_results"
             " WHERE test_run_id = (SELECT MAX(test_run_id) FROM test_runs) ORDER BY scenario_code")
    guards = q("SELECT scenario_code, MAX(failure_category) AS guarded_risk FROM test_results GROUP BY 1")
    import sys
    sys.path.insert(0, str(ROOT))
    from tests.e2e.scenarios import SCENARIOS
    risk = {code: cat for code, _n, _f, _e, cat, _fn in SCENARIOS}
    scen["guarded_risk"] = scen.scenario_code.map(risk).str.replace("_", " ")
    scen["scenario_number"] = scen.scenario_code.str[-3:].astype(int)
    scen["scenario_label"] = scen.scenario_code + " " + scen.scenario_name
    del guards

    # ------------------------------------------------------------------ facts
    runs = q("SELECT r.*, d.detected_format, d.sample_variant, d.document_role FROM ai_runs r"
             " JOIN documents d USING (document_id)")
    fact_runs = pd.DataFrame({
        "ai_run_id": runs.ai_run_id,
        "date_key": date_key(runs.started_at),
        "document_type_id": [doc_key[(f, v)] for f, v in zip(runs.detected_format, runs.sample_variant)],
        "provider_id": runs.provider_used.map(lambda p: prov_key.get(p, 3)),
        "task": runs.task.str.replace("_", " "),
        "document_role": runs.document_role,
        "status": runs.status,
        "is_success": (runs.status == "success").astype(int),
        "is_error": (runs.status == "error").astype(int),
        "error_stage": runs.error_stage.fillna("").str.replace("_", " "),
        "error_code": runs.error_code.fillna(""),
        "fallback_used": runs.fallback_used,
        "fallback_reason": runs.fallback_reason.fillna(""),
        "confidence_score": runs.confidence_score,
        # numbered labels so that the bands sort in order; failed runs have no confidence at all
        "confidence_band": pd.cut(runs.confidence_score, [-0.01, 0.6, 0.7, 0.8, 0.9, 1.01], right=False,
                                  labels=["1. < 0.60", "2. 0.60-0.69", "3. 0.70-0.79", "4. 0.80-0.89",
                                          "5. >= 0.90"]).astype(object).fillna("0. no output (error)"),
        "intake_status": runs.intake_status.fillna(""),
        "needs_review": ((runs.task == "extraction") & (runs.status == "success")
                         & (runs.intake_status != "Complete")).astype(int),
        "missing_count": runs.missing_count,
        "conflict_count": runs.conflict_count,
        "processing_ms": runs.processing_ms.round(1),
        "latency_is_simulated": runs.latency_is_simulated,
        "is_retry": runs.retry_of_run_id.notna().astype(int),
        "case_id": runs.case_id,
    })

    # summaries and assistant answers carry no confidence: not an error
    fact_runs.loc[(runs.task != "extraction") & runs.confidence_score.isna(), "confidence_band"] = "not applicable"

    fields = q("SELECT f.*, e.started_at, e.detected_format, e.sample_variant, e.provider_used"
               " FROM extracted_fields f JOIN vw_extraction_runs e ON e.ai_run_id = f.ai_run_id")
    fact_fields = pd.DataFrame({
        "field_id": fields.field_id, "ai_run_id": fields.ai_run_id, "date_key": date_key(fields.started_at),
        "document_type_id": [doc_key[(f, v)] for f, v in zip(fields.detected_format, fields.sample_variant)],
        "provider_id": fields.provider_used.map(lambda p: prov_key.get(p, 3)),
        "field_name": fields.field_name, "field_label": fields.field_name.map(FIELD_LABELS),
        "confidence": fields.confidence.round(3), "is_missing": fields.is_missing, "has_conflict": fields.has_conflict,
        "expected_present": fields.expected_value.notna().astype(int),
        "found_when_present": (fields.expected_value.notna() & fields.ai_value.notna()).astype(int),
        "is_scored": fields.is_correct.notna().astype(int), "is_correct": fields.is_correct,
        "is_reviewed": fields.was_corrected.notna().astype(int), "was_corrected": fields.was_corrected,
    })

    reviews = q("SELECT h.*, c.intake_status, d.detected_format, d.sample_variant FROM human_reviews h"
                " JOIN cases c USING (case_id) JOIN documents d ON d.document_id = c.source_document_id")
    fact_reviews = pd.DataFrame({
        "review_id": reviews.review_id, "case_id": reviews.case_id, "date_key": date_key(reviews.reviewed_at),
        "document_type_id": [doc_key[(f, v)] for f, v in zip(reviews.detected_format, reviews.sample_variant)],
        "reviewer": reviews.reviewer, "review_type": reviews.review_type.str.replace("_", " "),
        "decision": reviews.decision, "intake_status": reviews.intake_status,
        "fields_reviewed": reviews.fields_reviewed, "fields_corrected": reviews.fields_corrected,
        "category_changed": reviews.category_changed, "review_seconds": reviews.review_seconds,
        "is_simulated": reviews.is_simulated,
    })

    tests = q("SELECT r.*, t.run_label, t.code_version, t.bug_replay, t.started_at FROM test_results r"
              " JOIN test_runs t USING (test_run_id)")
    fact_tests = pd.DataFrame({
        "result_id": tests.result_id, "test_run_id": tests.test_run_id,
        "run_label": "#" + tests.test_run_id.astype(str) + " " + tests.code_version,
        "run_description": tests.run_label, "run_order": tests.test_run_id,
        "date_key": date_key(tests.started_at), "scenario_code": tests.scenario_code,
        "status": tests.status, "is_pass": (tests.status == "PASS").astype(int),
        "is_fail": (tests.status == "FAIL").astype(int), "is_regression": tests.is_regression,
        # risk area guarded by the scenario (same for PASS and FAIL rows, so zero-failure areas show as 0)
        "failure_category": tests.scenario_code.map(risk).str.replace("_", " "),
        "bug_replay": tests.bug_replay.fillna("none"), "duration_ms": tests.duration_ms,
    })

    audit = q("SELECT event_id, event_time, event_type, entity_type, processing_status, error_code FROM audit_events")
    fact_audit = pd.DataFrame({
        "event_id": audit.event_id, "date_key": date_key(audit.event_time), "event_type": audit.event_type,
        "event_group": audit.event_type.map(EVENT_GROUPS).fillna("Other"),
        "entity_type": audit.entity_type.fillna(""), "processing_status": audit.processing_status.fillna(""),
        "error_code": audit.error_code.fillna(""),
    })

    tables = {"DimDate": dim_date, "DimDocumentType": dim_doc, "DimAIProvider": dim_provider,
              "DimTestScenario": scen[["scenario_code", "scenario_number", "scenario_name", "scenario_label",
                                       "document_format", "expected", "guarded_risk"]],
              "FactAIRuns": fact_runs, "FactFieldExtraction": fact_fields, "FactHumanReview": fact_reviews,
              "FactTestResults": fact_tests, "FactAuditEvents": fact_audit}
    for df in tables.values():  # integer columns with blanks stay integers in the CSV
        for col in df.columns:
            if df[col].dtype == "float64" and df[col].dropna().mod(1).eq(0).all() and col not in (
                    "confidence_score", "confidence", "processing_ms", "duration_ms"):
                df[col] = df[col].astype("Int64")
    for p in OUT.glob("*.csv"):
        p.unlink()
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False, lineterminator="\n")
        print(f"  {name:22} {len(df):6} rows")
    conn.close()


if __name__ == "__main__":
    main()
