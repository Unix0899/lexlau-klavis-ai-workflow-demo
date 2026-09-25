"""Build the Power BI layer from ONE definition (this file):

  powerbi/DAX_MEASURES.md                    documentation of every measure
  powerbi/tmdl_measures_script.tmdl          script to paste in Power BI Desktop > TMDL view
  powerbi/Klavis_AI_Quality/                 Power BI Project (PBIP), opens in Power BI Desktop:
      Klavis_AI_Quality.pbip
      Klavis_AI_Quality.SemanticModel/       TMDL: 9 tables, types, relationships, measures
      Klavis_AI_Quality.Report/              5-page report (powerbi/DASHBOARD_SPEC.md)

A .pbix is a binary Power BI Desktop file: it is produced from the PBIP with File > Save as
(it cannot be written reliably by a script). The CSV folder is a model parameter (DataFolder).
"""
import json
import shutil
import sys
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from powerbi_report import NAVY, RED, TEAL, GREY, AMBER, Report, bar_objects, color, lit, text, TRUE  # noqa: E402

DISCLOSURE = ("Synthetic demonstration data. No real client, legal-case or confidential "
              "LexLau/Klavis data is included.")
PBI = ROOT / "powerbi"
DATA = PBI / "data"
NAME = "Klavis_AI_Quality"
PROJECT = PBI / NAME
EXTRACTION = 'FactAIRuns[task] = "extraction"'

# --------------------------------------------------------------------------- measures (single source of truth)
# (table, name, dax, format, folder, description)
MEASURES = [
    # 1 AI runs
    ("FactAIRuns", "Total AI Runs", "COUNTROWS ( FactAIRuns )", "#,0", "1 AI runs",
     "All AI runs: extraction, category suggestion, summarisation, assistant."),
    ("FactAIRuns", "Successful AI Runs", 'CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[status] = "success" )',
     "#,0", "1 AI runs", ""),
    ("FactAIRuns", "Failed AI Runs", 'CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[status] = "error" )',
     "#,0", "1 AI runs", "Runs that ended in a structured error."),
    ("FactAIRuns", "AI Success Rate %", "DIVIDE ( [Successful AI Runs], [Total AI Runs] )", "0.0%", "1 AI runs",
     "Successful / all AI runs in context."),
    ("FactAIRuns", "Extraction Runs", f"CALCULATE ( COUNTROWS ( FactAIRuns ), {EXTRACTION} )", "#,0", "1 AI runs", ""),
    ("FactAIRuns", "Successful Extractions",
     f'CALCULATE ( COUNTROWS ( FactAIRuns ), {EXTRACTION}, FactAIRuns[status] = "success" )', "#,0", "1 AI runs", ""),
    ("FactAIRuns", "Extraction Success Rate %", "DIVIDE ( [Successful Extractions], [Extraction Runs] )", "0.0%",
     "1 AI runs", "Document success rate: extraction runs processed without error (same as the app KPI)."),
    ("FactAIRuns", "Average Confidence",
     f'CALCULATE ( AVERAGE ( FactAIRuns[confidence_score] ), {EXTRACTION}, FactAIRuns[status] = "success" )',
     "0.00", "1 AI runs", "Mean overall confidence of successful extractions (demonstration metric)."),
    ("FactAIRuns", "Average Processing Time",
     f"CALCULATE ( AVERAGE ( FactAIRuns[processing_ms] ), {EXTRACTION} )", "#,0", "1 AI runs",
     "Milliseconds. Latency of extraction runs. In the synthetic dataset it comes from a latency model (flagged per run)."),
    ("FactAIRuns", "Fallback Runs", f"CALCULATE ( COUNTROWS ( FactAIRuns ), {EXTRACTION}, FactAIRuns[fallback_used] = 1 )",
     "#,0", "1 AI runs", "Extraction runs where the primary provider failed and the fallback was invoked."),
    ("FactAIRuns", "Fallback Rate %", "DIVIDE ( [Fallback Runs], [Extraction Runs] )", "0.0%", "1 AI runs", ""),
    ("FactAIRuns", "Error Rate %", "DIVIDE ( CALCULATE ( [Failed AI Runs], " + EXTRACTION + " ), [Extraction Runs] )",
     "0.0%", "1 AI runs", "Extraction runs ended in error."),
    ("FactAIRuns", "Human Review Cases", "CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[needs_review] = 1 )",
     "#,0", "1 AI runs", "Successful extractions flagged Needs Review or Missing Information."),
    ("FactAIRuns", "Human Review Rate %", "DIVIDE ( [Human Review Cases], [Successful Extractions] )", "0.0%",
     "1 AI runs", ""),
    ("FactAIRuns", "PDF Success Rate %",
     'CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "PDF" )', "0.0%", "1 AI runs", ""),
    ("FactAIRuns", "DOCX Success Rate %",
     'CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "DOCX" )', "0.0%", "1 AI runs", ""),
    ("FactAIRuns", "Image Success Rate %",
     'CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "Image" )', "0.0%", "1 AI runs", ""),
    # 2 Field quality
    ("FactFieldExtraction", "Scored Fields", "SUM ( FactFieldExtraction[is_scored] )", "#,0", "2 Field quality",
     "Fields compared with the ground truth."),
    ("FactFieldExtraction", "Correct Fields", "SUM ( FactFieldExtraction[is_correct] )", "#,0", "2 Field quality", ""),
    ("FactFieldExtraction", "Field Accuracy %", "DIVIDE ( [Correct Fields], [Scored Fields] )", "0.0%",
     "2 Field quality", "Correct fields / scored fields (null = null counts as correct)."),
    ("FactFieldExtraction", "Completeness %",
     "DIVIDE ( SUM ( FactFieldExtraction[found_when_present] ), SUM ( FactFieldExtraction[expected_present] ) )",
     "0.0%", "2 Field quality", "Share of the fields present in the document that the extraction found."),
    ("FactFieldExtraction", "Missing Fields", "SUM ( FactFieldExtraction[is_missing] )", "#,0", "2 Field quality",
     "Fields reported missing (absent from the document or not found)."),
    ("FactFieldExtraction", "Missing Rate %", "DIVIDE ( [Missing Fields], COUNTROWS ( FactFieldExtraction ) )",
     "0.0%", "2 Field quality", ""),
    ("FactFieldExtraction", "Conflicting Fields", "SUM ( FactFieldExtraction[has_conflict] )", "#,0",
     "2 Field quality", "Fields with contradictory values in the document."),
    ("FactFieldExtraction", "Avg Field Confidence",
     "CALCULATE ( AVERAGE ( FactFieldExtraction[confidence] ), FactFieldExtraction[is_missing] = 0 )", "0.00",
     "2 Field quality", "Average confidence of the fields that were found."),
    ("FactFieldExtraction", "Manual Corrections", "SUM ( FactFieldExtraction[was_corrected] )", "#,0",
     "2 Field quality", "Fields changed by the reviewer before the case was created."),
    ("FactFieldExtraction", "Manual Correction Rate %",
     "DIVIDE ( [Manual Corrections], SUM ( FactFieldExtraction[is_reviewed] ) )", "0.0%", "2 Field quality", ""),
    # 3 Testing
    ("FactTestResults", "Tests Executed", "COUNTROWS ( FactTestResults )", "#,0", "3 Testing", ""),
    ("FactTestResults", "Tests Passed", "SUM ( FactTestResults[is_pass] )", "#,0", "3 Testing", ""),
    ("FactTestResults", "Tests Failed", "SUM ( FactTestResults[is_fail] )", "#,0", "3 Testing", ""),
    ("FactTestResults", "Test Pass Rate %", "DIVIDE ( [Tests Passed], [Tests Executed] )", "0.0%", "3 Testing", ""),
    ("FactTestResults", "Regression Failures", "SUM ( FactTestResults[is_regression] )", "#,0", "3 Testing",
     "A scenario that passed in the previous run and fails now."),
    ("FactTestResults", "Latest Test Pass Rate %",
     "VAR LastRun = CALCULATE ( MAX ( FactTestResults[run_order] ), ALL ( FactTestResults ) )\nRETURN\n"
     "    CALCULATE ( [Test Pass Rate %], FactTestResults[run_order] = LastRun )", "0.0%", "3 Testing",
     "Pass rate of the most recent test run (use on cards)."),
    ("FactTestResults", "Test Runs", "DISTINCTCOUNT ( FactTestResults[test_run_id] )", "#,0", "3 Testing", ""),
    # 4 Human review & data quality
    ("FactHumanReview", "Reviews",
     'CALCULATE ( COUNTROWS ( FactHumanReview ), FactHumanReview[review_type] = "intake validation" )', "#,0",
     "4 Human review", "Intake validations (one per created case)."),
    ("FactHumanReview", "Reviews With Corrections",
     'CALCULATE ( [Reviews], FactHumanReview[decision] = "Approved with corrections" )', "#,0", "4 Human review", ""),
    ("FactHumanReview", "Reviews With Corrections %", "DIVIDE ( [Reviews With Corrections], [Reviews] )", "0.0%",
     "4 Human review", ""),
    ("FactHumanReview", "Avg Review Time",
     'CALCULATE ( AVERAGE ( FactHumanReview[review_seconds] ), FactHumanReview[review_type] = "intake validation" )',
     "0", "4 Human review", "Seconds. Simulated reviewers in the synthetic dataset."),
    ("FactHumanReview", "Category Changes", "SUM ( FactHumanReview[category_changed] )", "#,0", "4 Human review", ""),
    ("FactAuditEvents", "Audit Events", "COUNTROWS ( FactAuditEvents )", "#,0", "4 Human review", ""),
    ("FactAuditEvents", "Files Rejected",
     'CALCULATE ( COUNTROWS ( FactAuditEvents ), FactAuditEvents[event_type] = "file_rejected" )', "#,0",
     "4 Human review", "Invalid or oversized uploads refused before any AI run."),
    ("FactAuditEvents", "Duplicates Blocked",
     'CALCULATE ( COUNTROWS ( FactAuditEvents ), FactAuditEvents[event_group] = "Duplicate prevention" )', "#,0",
     "4 Human review", "Duplicate case blocked + repeated submission ignored."),
]

PANDAS_TO_TMDL = {"int64": ("int64", "Int64.Type"), "float64": ("double", "type number"),
                  "object": ("string", "type text"), "str": ("string", "type text"), "string": ("string", "type text")}
KEY_COLUMNS = {"DimDate": "date", "DimDocumentType": "document_type_id", "DimAIProvider": "provider_id",
               "DimTestScenario": "scenario_code"}
HIDDEN = {"date_key", "document_type_id", "provider_id", "family_order", "variant_order", "run_order",
          "scenario_number", "ai_run_id", "field_id", "review_id", "result_id", "event_id", "case_id", "test_run_id"}
SORT_BY = {("DimDocumentType", "document_type"): "document_type_id", ("DimDocumentType", "file_family"): "family_order",
           ("DimTestScenario", "scenario_label"): "scenario_number", ("DimTestScenario", "scenario_name"): "scenario_number",
           ("FactTestResults", "run_label"): "run_order", ("DimDate", "month_name"): "month"}

RELATIONSHIPS = [  # (from table, from column, to table, to column)
    ("FactAIRuns", "date_key", "DimDate", "date_key"),
    ("FactAIRuns", "document_type_id", "DimDocumentType", "document_type_id"),
    ("FactAIRuns", "provider_id", "DimAIProvider", "provider_id"),
    ("FactFieldExtraction", "date_key", "DimDate", "date_key"),
    ("FactFieldExtraction", "document_type_id", "DimDocumentType", "document_type_id"),
    ("FactFieldExtraction", "provider_id", "DimAIProvider", "provider_id"),
    ("FactHumanReview", "date_key", "DimDate", "date_key"),
    ("FactHumanReview", "document_type_id", "DimDocumentType", "document_type_id"),
    ("FactTestResults", "date_key", "DimDate", "date_key"),
    ("FactTestResults", "scenario_code", "DimTestScenario", "scenario_code"),
    ("FactAuditEvents", "date_key", "DimDate", "date_key"),
]
ORDER = ["DimDate", "DimDocumentType", "DimAIProvider", "DimTestScenario", "FactAIRuns", "FactFieldExtraction",
         "FactHumanReview", "FactTestResults", "FactAuditEvents"]
PAGES = ["AI Quality Overview", "Document Extraction", "Field Quality", "Testing & Reliability",
         "Human Review & Data Quality"]


def tag() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "klavis-demo-" + str(next(tag.counter))))


tag.counter = iter(range(1, 100000))


def tmdl_table(name: str, df: pd.DataFrame) -> str:
    lines = [f"table {name}", f"\tlineageTag: {tag()}", ""]
    for t, m, dax, fmt, folder, desc in MEASURES:
        if t != name:
            continue
        if desc:
            lines.append(f"\t/// {desc}")
        if "\n" in dax:
            lines.append(f"\tmeasure '{m}' =")
            lines += ["\t\t\t" + d for d in dax.split("\n")]
        else:
            lines.append(f"\tmeasure '{m}' = {dax}")
        lines += [f"\t\tformatString: {json.dumps(fmt)}", f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag()}", ""]
    types = []
    for col, dtype in df.dtypes.items():
        whole = str(dtype) == "float64" and (df[col].dropna() % 1 == 0).all() and col not in (
            "confidence_score", "confidence", "processing_ms", "duration_ms")
        if name == "DimDate" and col in ("date", "week_start"):
            tm, mt = "dateTime", "type date"
        elif whole:
            tm, mt = "int64", "Int64.Type"
        else:
            tm, mt = PANDAS_TO_TMDL.get(str(dtype), ("string", "type text"))
        types.append((col, mt))
        lines += [f"\tcolumn {col}", f"\t\tdataType: {tm}"]
        if tm == "dateTime":
            lines.append("\t\tformatString: dd/mm/yyyy")
        if KEY_COLUMNS.get(name) == col:
            lines.append("\t\tisKey")
        if col in HIDDEN or col.startswith(("is_", "has_", "expected_present", "found_when")):
            lines.append("\t\tisHidden")
        lines.append(f"\t\tsummarizeBy: {'none' if tm != 'double' else 'sum'}")
        if (name, col) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(name, col)]}")
        lines += [f"\t\tsourceColumn: {col}", f"\t\tlineageTag: {tag()}", ""]
    type_list = ", ".join(f'{{"{c}", {t}}}' for c, t in types)
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), '
              '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
              "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
              "\t\t\t\t    EmptyToNull = Table.ReplaceValue(Promoted, \"\", null, Replacer.ReplaceValue, "
              "Table.ColumnNames(Promoted)),",
              f'\t\t\t\t    Typed = Table.TransformColumnTypes(EmptyToNull, {{{type_list}}}, "en-US")',
              "\t\t\t\tin", "\t\t\t\t    Typed", ""]
    if name == "DimDate":
        lines.insert(2, "\tdataCategory: Time")
    return "\n".join(lines)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- report pages
def build_report():
    home = {m: t for t, m, *_ in MEASURES}
    month = ("c", "DimDate", "year_month")
    family = ("c", "DimDocumentType", "file_family")
    r = Report(home, [("Month", month), ("File type", family), ("Provider", ("c", "DimAIProvider", "provider_name"))],
               DISCLOSURE + " Public reconstruction - not the Klavis production system. "
               "Latency and reviewers are simulated in the dataset.")
    M = lambda n: ("m", n)  # noqa: E731
    ref = r.ref
    doc_type = ("c", "DimDocumentType", "document_type")
    field = ("c", "FactFieldExtraction", "field_label")

    # 1 ------------------------------------------------------------------ AI quality overview
    p = r.page("AI Quality Overview", "Does the AI workflow produce reliable, reviewable case data?")
    r.cards(p, ["Total AI Runs", "AI Success Rate %", "Field Accuracy %", "Average Confidence", "Human Review Rate %",
                "Latest Test Pass Rate %"])
    r.visual(p, "columnChart", 16, 170, 616, 256,
             {"Category": [month], "Series": [("c", "FactAIRuns", "status")], "Y": [M("Total AI Runs")]},
             title="AI runs over time: success vs failure", order_by=month, descending=False,
             objects={"categoryAxis": [{"properties": {"showAxisTitle": lit("false")}}],
                      "valueAxis": [{"properties": {"showAxisTitle": lit("false")}}],
                      "labels": [{"properties": {"show": TRUE}}]})
    r.visual(p, "donutChart", 644, 170, 300, 256, {"Category": [("c", "FactAIRuns", "task")], "Y": [M("Total AI Runs")]},
             title="AI runs by task", objects={"labels": [{"properties": {"show": TRUE, "labelStyle": text("Data value")}}]})
    r.visual(p, "clusteredColumnChart", 956, 170, 308, 256,
             {"Category": [("c", "FactAIRuns", "confidence_band")], "Y": [M("Extraction Runs")]},
             title="Confidence distribution (extractions)", order_by=("c", "FactAIRuns", "confidence_band"),
             descending=False, objects=bar_objects(fill=NAVY))
    r.visual(p, "clusteredBarChart", 16, 438, 616, 250,
             {"Category": [family], "Y": [M("Extraction Success Rate %"), M("Field Accuracy %")]},
             title="Performance by file type: success rate and field accuracy", order_by=family, descending=False,
             objects=bar_objects(series_colors={ref(M("Extraction Success Rate %")): TEAL,
                                                ref(M("Field Accuracy %")): NAVY}, percent=True))
    r.visual(p, "tableEx", 644, 438, 620, 250,
             {"Values": [doc_type, M("Extraction Runs"), M("Extraction Success Rate %"), M("Field Accuracy %"),
                         M("Average Confidence"), M("Human Review Rate %")]},
             title="Quality by document type", order_by=doc_type, descending=False)

    # 2 ------------------------------------------------------------------ document extraction
    p = r.page("Document Extraction", "Do PDF, DOCX and images go through the workflow equally well?")
    r.cards(p, ["PDF Success Rate %", "DOCX Success Rate %", "Image Success Rate %", "Completeness %",
                "Average Processing Time", "Manual Correction Rate %"])
    r.visual(p, "lineChart", 16, 170, 616, 256,
             {"Category": [month], "Y": [M("PDF Success Rate %"), M("DOCX Success Rate %"), M("Image Success Rate %")]},
             title="Success rate by month and file type (DOCX routing bug fixed mid-February)", order_by=month,
             descending=False,
             objects={"dataPoint": [{"properties": {"fill": color(NAVY)}, "selector": {"metadata": ref(M("PDF Success Rate %"))}},
                                    {"properties": {"fill": color(RED)}, "selector": {"metadata": ref(M("DOCX Success Rate %"))}},
                                    {"properties": {"fill": color(TEAL)}, "selector": {"metadata": ref(M("Image Success Rate %"))}}],
                      "lineStyles": [{"properties": {"strokeWidth": lit("3D")}}],
                      "categoryAxis": [{"properties": {"showAxisTitle": lit("false")}}],
                      "valueAxis": [{"properties": {"showAxisTitle": lit("false")}}]})
    r.visual(p, "clusteredColumnChart", 644, 170, 620, 256,
             {"Category": [("c", "DimDocumentType", "detected_format")], "Y": [M("Average Processing Time")]},
             title="Average processing time by format (ms)", order_by=M("Average Processing Time"), descending=False,
             objects=bar_objects(fill=NAVY))
    r.visual(p, "tableEx", 16, 438, 1248, 250,
             {"Values": [doc_type, M("Extraction Runs"), M("Extraction Success Rate %"), M("Field Accuracy %"),
                         M("Completeness %"), M("Manual Correction Rate %"), M("Fallback Rate %"),
                         M("Average Processing Time")]},
             title="Success rate, field accuracy, completeness, latency and manual correction by document type",
             order_by=doc_type, descending=False)

    # 3 ------------------------------------------------------------------ field quality
    p = r.page("Field Quality", "Which fields can be trusted, and which ones need the reviewer?")
    r.cards(p, ["Field Accuracy %", "Completeness %", "Missing Fields", "Conflicting Fields", "Manual Corrections",
                "Avg Field Confidence"])
    r.visual(p, "clusteredBarChart", 16, 170, 400, 518, {"Category": [field], "Y": [M("Field Accuracy %")]},
             title="Accuracy by field", order_by=M("Field Accuracy %"), descending=False,
             objects=bar_objects(percent=True))
    r.visual(p, "clusteredBarChart", 428, 170, 412, 254, {"Category": [field], "Y": [M("Missing Rate %")]},
             title="Missing rate by field", order_by=M("Missing Rate %"), objects=bar_objects(fill=AMBER, percent=True))
    r.visual(p, "clusteredBarChart", 852, 170, 412, 254, {"Category": [field], "Y": [M("Manual Corrections")]},
             title="Manual corrections by field", order_by=M("Manual Corrections"), objects=bar_objects(fill=NAVY))
    r.visual(p, "pivotTable", 428, 436, 836, 252,
             {"Rows": [field], "Columns": [family], "Values": [M("Field Accuracy %")]},
             title="Field accuracy by file type")

    # 4 ------------------------------------------------------------------ testing & reliability
    p = r.page("Testing & Reliability", "Do fixes hold, and does the workflow fail safely?")
    r.cards(p, ["Tests Executed", "Tests Passed", "Tests Failed", "Test Pass Rate %", "Regression Failures",
                "Fallback Rate %"])
    run = ("c", "FactTestResults", "run_label")
    r.visual(p, "lineClusteredColumnComboChart", 16, 170, 616, 256,
             {"Category": [run], "Y": [M("Tests Failed")], "Y2": [M("Test Pass Rate %")]},
             title="Test runs: pass rate (line) and failed scenarios (columns)", order_by=run, descending=False,
             objects={"dataPoint": [{"properties": {"fill": color(RED)}, "selector": {"metadata": ref(M("Tests Failed"))}},
                                    {"properties": {"fill": color(TEAL)}, "selector": {"metadata": ref(M("Test Pass Rate %"))}}],
                      "lineStyles": [{"properties": {"strokeWidth": lit("3D")}}],
                      "labels": [{"properties": {"show": TRUE}}]})
    r.visual(p, "clusteredBarChart", 644, 170, 620, 256,
             {"Category": [("c", "DimTestScenario", "scenario_label")], "Y": [M("Tests Failed")]},
             title="Failures by scenario (all runs)", order_by=("c", "DimTestScenario", "scenario_label"),
             descending=False, objects=bar_objects(fill=RED))
    r.visual(p, "clusteredBarChart", 16, 438, 400, 250,
             {"Category": [("c", "FactTestResults", "failure_category")], "Y": [M("Tests Failed")]},
             title="Failure categories", order_by=M("Tests Failed"), objects=bar_objects(fill=RED))
    r.visual(p, "clusteredBarChart", 428, 438, 412, 250,
             {"Category": [("c", "FactAIRuns", "fallback_reason")], "Y": [M("Fallback Runs")]},
             title="Fallback usage by primary failure", order_by=M("Fallback Runs"), objects=bar_objects(fill=AMBER))
    r.visual(p, "clusteredBarChart", 852, 438, 412, 250,
             {"Category": [("c", "FactAIRuns", "error_code")], "Y": [M("Failed AI Runs")]},
             title="Processing errors by code", order_by=M("Failed AI Runs"), objects=bar_objects(fill=NAVY))

    # 5 ------------------------------------------------------------------ human review & data quality
    p = r.page("Human Review & Data Quality", "Where does the human stay in the loop, and what does the audit show?")
    r.cards(p, ["Human Review Cases", "Reviews", "Manual Corrections", "Missing Fields", "Files Rejected",
                "Duplicates Blocked"])
    r.visual(p, "lineClusteredColumnComboChart", 16, 170, 616, 256,
             {"Category": [month], "Y": [M("Reviews")], "Y2": [M("Reviews With Corrections %")]},
             title="Reviews per month (columns) and share with corrections (line)", order_by=month, descending=False,
             objects={"dataPoint": [{"properties": {"fill": color(GREY)}, "selector": {"metadata": ref(M("Reviews"))}},
                                    {"properties": {"fill": color(TEAL)}, "selector": {"metadata": ref(M("Reviews With Corrections %"))}}],
                      "lineStyles": [{"properties": {"strokeWidth": lit("3D")}}]})
    r.visual(p, "clusteredBarChart", 644, 170, 620, 256,
             {"Category": [("c", "FactHumanReview", "intake_status")], "Y": [M("Reviews"), M("Reviews With Corrections")]},
             title="Cases by intake status: reviewed and corrected", order_by=M("Reviews"),
             objects=bar_objects(series_colors={ref(M("Reviews")): GREY, ref(M("Reviews With Corrections")): TEAL}))
    r.visual(p, "clusteredBarChart", 16, 438, 400, 250, {"Category": [field], "Y": [M("Missing Fields")]},
             title="Missing fields (data-quality issues)", order_by=M("Missing Fields"), objects=bar_objects(fill=AMBER))
    r.visual(p, "clusteredBarChart", 428, 438, 412, 250,
             {"Category": [("c", "FactAuditEvents", "event_group")], "Y": [M("Audit Events")]},
             title="Audit events by group (metadata only)", order_by=M("Audit Events"), objects=bar_objects(fill=NAVY))
    r.visual(p, "tableEx", 852, 438, 412, 250,
             {"Values": [("c", "FactAuditEvents", "event_type"), M("Audit Events")]},
             title="Privacy / audit events", order_by=M("Audit Events"))
    return r.build()


def build_project(tables):
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    sm, rp = PROJECT / f"{NAME}.SemanticModel", PROJECT / f"{NAME}.Report"
    write(PROJECT / f"{NAME}.pbip", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2))
    write(sm / "definition.pbism", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {"qnaEnabled": False}}, indent=2))
    write(sm / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    write(sm / "definition" / "expressions.tmdl",
          "/// Folder that contains the CSV exports (powerbi/data). Change it after cloning the repository.\n"
          f'expression DataFolder = "{DATA}\\" meta [IsParameterQuery = true, Type = "Text", '
          'IsParameterQueryRequired = true]\n'
          f"\tlineageTag: {tag()}\n")
    model = [f"/// {DISCLOSURE}", "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-US", "",
             "\tannotation Disclosure = Synthetic data - public reconstruction, not Klavis production data", ""]
    model += [f"ref table {t}" for t in tables]
    write(sm / "definition" / "model.tmdl", "\n".join(model) + "\n")
    for name, df in tables.items():
        write(sm / "definition" / "tables" / f"{name}.tmdl", tmdl_table(name, df))
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag()}", f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    write(sm / "definition" / "relationships.tmdl", "\n".join(rel))
    write(rp / "definition.pbir", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2))
    report = build_report()
    assert [s["displayName"] for s in report["sections"]] == PAGES
    write(rp / "report.json", json.dumps(report, indent=2, ensure_ascii=False))


def write_docs():
    lines = ["# DAX measures", "", f"> {DISCLOSURE}", "",
             f"{len(MEASURES)} measures, generated from `scripts/build_powerbi_project.py` (one definition produces this "
             "page, the TMDL model of the PBIP and the paste-in script `tmdl_measures_script.tmdl`).", "",
             "Conventions: `DIVIDE()` everywhere; rates are ratios formatted as %; run-level quality measures "
             "(confidence, latency, fallback, human review) are computed on **extraction** runs; field measures on "
             "`FactFieldExtraction`; every definition matches the SQL views in `sql/views.sql` "
             "(see `docs/AI_QUALITY_FRAMEWORK.md`).", ""]
    folder = None
    for t, m, dax, fmt, f, desc in MEASURES:
        if f != folder:
            lines += [f"## {f[2:]}", ""]
            folder = f
        lines += [f"### {m}", "", f"Table `{t}` · format `{fmt}`" + (f" · {desc}" if desc else ""), "",
                  "```DAX", f"{m} =", *("    " + d for d in dax.split("\n")), "```", ""]
    write(PBI / "DAX_MEASURES.md", "\n".join(lines))
    script = ["createOrReplace", ""]
    for t, m, dax, fmt, f, desc in MEASURES:
        script += [f"\tref table {t}", ""]
        if "\n" in dax:
            script += [f"\t\tmeasure '{m}' ="] + ["\t\t\t\t" + d for d in dax.split("\n")]
        else:
            script.append(f"\t\tmeasure '{m}' = {dax}")
        script += [f"\t\t\tformatString: {json.dumps(fmt)}", f"\t\t\tdisplayFolder: {f}", ""]
    write(PBI / "tmdl_measures_script.tmdl", "\n".join(script))


def check_names(tables):
    problems, seen = [], {}
    for t, m, *_ in MEASURES:
        if m.lower() in {c.lower() for c in tables[t].columns}:
            problems.append(f"measure '{m}' clashes with a column of {t}")
        if m.lower() in seen:
            problems.append(f"measure '{m}' defined twice")
        seen[m.lower()] = t
    for ft, fc, tt, tc in RELATIONSHIPS:
        if fc not in tables[ft].columns or tc not in tables[tt].columns:
            problems.append(f"relationship {ft}.{fc} -> {tt}.{tc}: unknown column")
        elif not set(tables[ft][fc].dropna()) <= set(tables[tt][tc]):
            problems.append(f"relationship {ft}.{fc} -> {tt}.{tc}: orphan keys")
    if problems:
        raise SystemExit("Model problems:\n  " + "\n  ".join(problems))


def main():
    tables = {name: pd.read_csv(DATA / f"{name}.csv", keep_default_na=True) for name in ORDER}
    check_names(tables)
    build_project(tables)
    write_docs()
    print(f"PBIP written: {PROJECT.relative_to(ROOT)} ({len(tables)} tables, {len(MEASURES)} measures, "
          f"{len(RELATIONSHIPS)} relationships, {len(PAGES)} pages)")


if __name__ == "__main__":
    main()
