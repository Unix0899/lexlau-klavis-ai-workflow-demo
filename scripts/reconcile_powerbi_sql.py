"""Reconcile the Power BI measures with SQL (requires the PBIP open in Power BI Desktop).

Connects READ-ONLY through Microsoft's Power BI Modeling MCP server, evaluates the DAX
measures, computes the same numbers in SQLite and writes docs/POWERBI_SQL_RECONCILIATION.md.

    python scripts/reconcile_powerbi_sql.py
"""
import csv
import io
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_powerbi_model import McpClient, find_server  # noqa: E402

DB = ROOT / "database" / "klavis_ai_demo.sqlite"
DISCLOSURE = ("Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data "
              "is included.")
TOL = 0.0005
EXT = "FROM ai_runs WHERE task = 'extraction'"
FAM = ("FROM ai_runs r JOIN documents d USING (document_id) WHERE r.task = 'extraction' AND "
       "CASE d.detected_format WHEN 'pdf' THEN 'PDF' WHEN 'docx' THEN 'DOCX' ELSE 'Image' END = '{f}'")
FF = "FROM extracted_fields f JOIN vw_extraction_runs e ON e.ai_run_id = f.ai_run_id"

GLOBAL = {
    "Total AI Runs": "SELECT COUNT(*) FROM ai_runs",
    "Successful AI Runs": "SELECT SUM(status='success') FROM ai_runs",
    "Failed AI Runs": "SELECT SUM(status='error') FROM ai_runs",
    "AI Success Rate %": "SELECT 1.0*SUM(status='success')/COUNT(*) FROM ai_runs",
    "Extraction Runs": f"SELECT COUNT(*) {EXT}",
    "Successful Extractions": f"SELECT SUM(status='success') {EXT}",
    "Extraction Success Rate %": f"SELECT 1.0*SUM(status='success')/COUNT(*) {EXT}",
    "Average Confidence": f"SELECT AVG(confidence_score) {EXT} AND status='success'",
    "Average Processing Time": f"SELECT AVG(processing_ms) {EXT}",
    "Fallback Runs": f"SELECT SUM(fallback_used) {EXT}",
    "Fallback Rate %": f"SELECT 1.0*SUM(fallback_used)/COUNT(*) {EXT}",
    "Error Rate %": f"SELECT 1.0*SUM(status='error')/COUNT(*) {EXT}",
    "Human Review Cases": f"SELECT SUM(status='success' AND intake_status<>'Complete') {EXT}",
    "Human Review Rate %": f"SELECT 1.0*SUM(status='success' AND intake_status<>'Complete')/SUM(status='success') {EXT}",
    "PDF Success Rate %": "SELECT 1.0*SUM(r.status='success')/COUNT(*) " + FAM.format(f="PDF"),
    "DOCX Success Rate %": "SELECT 1.0*SUM(r.status='success')/COUNT(*) " + FAM.format(f="DOCX"),
    "Image Success Rate %": "SELECT 1.0*SUM(r.status='success')/COUNT(*) " + FAM.format(f="Image"),
    "Scored Fields": f"SELECT COUNT(f.is_correct) {FF}",
    "Correct Fields": f"SELECT SUM(f.is_correct) {FF}",
    "Field Accuracy %": f"SELECT 1.0*SUM(f.is_correct)/COUNT(f.is_correct) {FF}",
    "Completeness %": f"SELECT 1.0*SUM(f.expected_value IS NOT NULL AND f.ai_value IS NOT NULL)"
                      f"/SUM(f.expected_value IS NOT NULL) {FF}",
    "Missing Fields": f"SELECT SUM(f.is_missing) {FF}",
    "Missing Rate %": f"SELECT 1.0*SUM(f.is_missing)/COUNT(*) {FF}",
    "Conflicting Fields": f"SELECT SUM(f.has_conflict) {FF}",
    "Avg Field Confidence": f"SELECT AVG(f.confidence) {FF} WHERE f.is_missing = 0",
    "Manual Corrections": f"SELECT SUM(f.was_corrected) {FF}",
    "Manual Correction Rate %": f"SELECT 1.0*SUM(f.was_corrected)/COUNT(f.was_corrected) {FF}",
    "Tests Executed": "SELECT COUNT(*) FROM test_results",
    "Tests Passed": "SELECT SUM(status='PASS') FROM test_results",
    "Tests Failed": "SELECT SUM(status='FAIL') FROM test_results",
    "Test Pass Rate %": "SELECT 1.0*SUM(status='PASS')/COUNT(*) FROM test_results",
    "Regression Failures": "SELECT SUM(is_regression) FROM test_results",
    "Latest Test Pass Rate %": "SELECT 1.0*tests_passed/tests_total FROM test_runs ORDER BY test_run_id DESC LIMIT 1",
    "Test Runs": "SELECT COUNT(*) FROM test_runs",
    "Reviews": "SELECT COUNT(*) FROM human_reviews WHERE review_type='intake_validation'",
    "Reviews With Corrections": "SELECT COUNT(*) FROM human_reviews WHERE review_type='intake_validation' "
                                "AND decision='Approved with corrections'",
    "Reviews With Corrections %": "SELECT 1.0*SUM(decision='Approved with corrections')/COUNT(*) FROM human_reviews "
                                  "WHERE review_type='intake_validation'",
    "Avg Review Time": "SELECT AVG(review_seconds) FROM human_reviews WHERE review_type='intake_validation'",
    "Category Changes": "SELECT SUM(category_changed) FROM human_reviews",
    "Audit Events": "SELECT COUNT(*) FROM audit_events",
    "Files Rejected": "SELECT COUNT(*) FROM audit_events WHERE event_type='file_rejected'",
    "Duplicates Blocked": "SELECT COUNT(*) FROM audit_events WHERE event_type IN "
                          "('duplicate_case_blocked','duplicate_submission_ignored')",
}
BY_FIELD_LABEL = {"Case title": "case_title", "Case reference": "case_reference", "Client": "client_name",
                  "Opposing party": "opposing_party", "Document type": "document_type",
                  "Jurisdiction": "jurisdiction", "Dates": "important_dates", "Amounts": "amounts",
                  "Category": "case_category"}


def parse(v):
    v = v.strip().strip('"')
    return None if v == "" else float(v.replace(" ", "").replace(" ", "").replace(",", "."))


def dax(client, query):
    reply = client.request("tools/call", {"name": "dax_query_operations",
                                          "arguments": {"request": {"operation": "Execute", "query": query}}})
    parts = reply["result"]["content"]
    status = json.loads(parts[0]["text"])
    if not status.get("success"):
        raise RuntimeError(status.get("message"))
    return list(csv.reader(io.StringIO(next(p["resource"]["text"] for p in parts if p.get("type") == "resource"))))


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(0.0005, TOL * abs(b))


def main():
    client = McpClient(find_server())
    client.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "klavis-demo-reconcile", "version": "1.0"}})
    client.request("notifications/initialized", notify=True)
    instances = client.tool("connection_operations", {"operation": "ListLocalInstances"})["data"]
    target = [i for i in instances if "Klavis_AI_Quality" in i.get("parentWindowTitle", "")]
    if not target:
        client.proc.kill()
        raise SystemExit("Open powerbi/Klavis_AI_Quality/Klavis_AI_Quality.pbip in Power BI Desktop first")
    client.tool("connection_operations", {"operation": "Connect", "connectionString": target[0]["connectionString"]})
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    one = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
    rows = []

    names = list(GLOBAL)
    values = dax(client, "EVALUATE ROW(" + ", ".join(f'"{m}", [{m}]' for m in names) + ")")[1]
    for m, v in zip(names, values):
        exp = one(GLOBAL[m])
        rows.append(("Whole dataset", m, parse(v), None if exp is None else float(exp)))

    fam = dax(client, 'EVALUATE SUMMARIZECOLUMNS(DimDocumentType[file_family], "runs", [Extraction Runs], '
                      '"ok", [Extraction Success Rate %], "acc", [Field Accuracy %])')
    for r in fam[1:]:
        f = r[0]
        cond = {"PDF": "e.detected_format='pdf'", "DOCX": "e.detected_format='docx'",
                "Image": "e.detected_format IN ('png','jpg')"}[f]
        rows.append((f, "Extraction Runs", parse(r[1]), one(f"SELECT COUNT(*) FROM vw_extraction_runs e WHERE {cond}")))
        rows.append((f, "Extraction Success Rate %", parse(r[2]),
                     one(f"SELECT 1.0*SUM(status='success')/COUNT(*) FROM vw_extraction_runs e WHERE {cond}")))
        rows.append((f, "Field Accuracy %", parse(r[3]),
                     one(f"SELECT 1.0*SUM(is_correct)/COUNT(is_correct) FROM vw_field_facts e WHERE {cond}")))

    by_field = dax(client, 'EVALUATE SUMMARIZECOLUMNS(FactFieldExtraction[field_label], "acc", [Field Accuracy %], '
                           '"miss", [Missing Fields], "corr", [Manual Corrections])')
    for r in by_field[1:]:
        sql = db.execute("SELECT accuracy_pct/100.0, (SELECT SUM(is_missing) FROM vw_field_facts WHERE field_name=?),"
                         " manual_corrections FROM vw_field_accuracy WHERE field_name=?",
                         (BY_FIELD_LABEL[r[0]], BY_FIELD_LABEL[r[0]])).fetchone()
        rows.append((r[0], "Field Accuracy %", parse(r[1]), sql[0]))
        rows.append((r[0], "Missing Fields", parse(r[2]), float(sql[1])))
        rows.append((r[0], "Manual Corrections", parse(r[3]), float(sql[2])))

    months = dax(client, 'EVALUATE SUMMARIZECOLUMNS(DimDate[year_month], "runs", [Total AI Runs])')
    for r in months[1:]:
        rows.append((r[0], "Total AI Runs", parse(r[1]),
                     float(one(f"SELECT COUNT(*) FROM ai_runs WHERE substr(started_at,1,7)='{r[0]}'"))))
    client.proc.kill()

    checked = [(s, m, g, e, close(g, e) if "Accuracy %" not in m or s == "Whole dataset" else
                (g is not None and e is not None and abs(g - e) <= 0.0006)) for s, m, g, e in rows]
    passed = sum(c[4] for c in checked)
    fmt = lambda v: "blank" if v is None else (f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}")  # noqa: E731
    lines = ["# Power BI ↔ SQL reconciliation", "", f"> {DISCLOSURE}", "",
             f"Run on {datetime.now():%d/%m/%Y %H:%M} with `scripts/reconcile_powerbi_sql.py`: the PBIP open in "
             "Power BI Desktop, queried **read-only** through Microsoft's Power BI Modeling MCP server, compared "
             "with the same numbers computed in SQLite.", "",
             f"**Result: {passed}/{len(checked)} comparisons PASS.** (SQL field accuracy by field is rounded "
             "to 0.1 % in the view, hence the 0.06-point tolerance on those rows.)", "",
             "| Scope | Measure | Power BI (DAX) | SQL | Status |", "|---|---|---:|---:|---|"]
    lines += [f"| {s} | {m} | {fmt(g)} | {fmt(e)} | {'PASS' if ok else 'FAIL'} |" for s, m, g, e, ok in checked]
    (ROOT / "docs" / "POWERBI_SQL_RECONCILIATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(checked)} PASS")
    for s, m, g, e, ok in checked:
        if not ok:
            print(f"FAIL {s:<16} {m:<26} DAX={g} SQL={e}")


if __name__ == "__main__":
    main()
