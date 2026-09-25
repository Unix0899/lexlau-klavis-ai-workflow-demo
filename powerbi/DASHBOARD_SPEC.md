# Klavis AI Quality Dashboard: specification (5 pages)

![Page 1](screenshots/powerbi_01_ai_quality_overview.png)

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Canvas 1280 × 720, light grey page, white cards, navy / teal. Every page has a title and question,
three synced slicers (**Month**, **File type**, **Provider**) and the disclosure in the footer. The
pages are already built in `Klavis_AI_Quality/Klavis_AI_Quality.Report/report.json`.

## Open it

1. Open `powerbi/Klavis_AI_Quality/Klavis_AI_Quality.pbip` in Power BI Desktop (File → Open).
2. If the repository is not at the path used when it was generated: *Transform data → Edit parameters →
   DataFolder* = `<repo>\powerbi\data\` (with the trailing backslash) → Apply.
3. *Refresh*. Optional: *File → Save as* → `Klavis_AI_Quality_Dashboard.pbix`.

## Page 1 · AI Quality Overview

*Does the AI workflow produce reliable, reviewable case data?*

| Visual | Fields |
|---|---|
| 6 cards | Total AI Runs · AI Success Rate % · Field Accuracy % · Average Confidence · Human Review Rate % · Latest Test Pass Rate % |
| Stacked columns: AI runs over time, success vs failure | DimDate[year_month] × FactAIRuns[status] → Total AI Runs |
| Donut: AI runs by task | FactAIRuns[task] → Total AI Runs |
| Columns: confidence distribution | FactAIRuns[confidence_band] → Extraction Runs |
| Bars: performance by file type | DimDocumentType[file_family] → Extraction Success Rate %, Field Accuracy % |
| Table: quality by document type | document type, runs, success, accuracy, confidence, review rate |

## Page 2 · Document Extraction

*Do PDF, DOCX and images go through the workflow equally well?*

| Visual | Fields |
|---|---|
| 6 cards | PDF Success Rate % · DOCX Success Rate % · Image Success Rate % · Completeness % · Average Processing Time · Manual Correction Rate % |
| Lines: success rate by month and file type | shows the DOCX drop in Jan-Feb and the recovery after the BUG-01 fix |
| Columns: average processing time by format | DimDocumentType[detected_format] |
| Table: success, accuracy, completeness, correction, fallback, latency by document type | |

## Page 3 · Field Quality

*Which fields can be trusted, and which ones need the reviewer?*

| Visual | Fields |
|---|---|
| 6 cards | Field Accuracy % · Completeness % · Missing Fields · Conflicting Fields · Manual Corrections · Avg Field Confidence |
| Bars: accuracy by field | client, opposing party, dates, amounts, jurisdiction, category, reference, title, document type |
| Bars: missing rate by field; manual corrections by field | |
| Matrix: field × file type → Field Accuracy % | |

## Page 4 · Testing & Reliability

*Do fixes hold, and does the workflow fail safely?*

| Visual | Fields |
|---|---|
| 6 cards | Tests Executed · Tests Passed · Tests Failed · Test Pass Rate % · Regression Failures · Fallback Rate % |
| Combo: test runs, pass rate (line) and failed scenarios (columns) | FactTestResults[run_label] (sorted by run) |
| Bars: failures by scenario | DimTestScenario[scenario_label] |
| Bars: failure categories; fallback usage by primary failure; processing errors by code | |

## Page 5 · Human Review & Data Quality

*Where does the human stay in the loop, and what does the audit show?*

| Visual | Fields |
|---|---|
| 6 cards | Human Review Cases · Reviews · Manual Corrections · Missing Fields · Files Rejected · Duplicates Blocked |
| Combo: reviews per month and share with corrections | |
| Bars: cases by intake status, reviewed vs corrected | FactHumanReview[intake_status] |
| Bars: missing fields (data-quality issues) | FactFieldExtraction[field_label] |
| Bars + table: privacy / audit events by group and type | FactAuditEvents |

## Expected headline values (whole dataset, no filter)

| Measure | Value | SQL source |
|---|---:|---|
| Total AI Runs | 892 | `ai_runs` |
| AI Success Rate % | 96.7% | all tasks |
| Extraction Success Rate % | 91.7% | `vw_ai_quality_summary` |
| Field Accuracy % | 92.9% | idem |
| Completeness % | 97.9% | idem |
| Average Confidence | 0.89 | idem |
| Human Review Rate % | 27.8% | idem |
| Fallback Rate % | 9.7% | idem |
| Manual Correction Rate % | 6.4% | idem |
| Latest Test Pass Rate % | 100% | `vw_test_run_summary` |
| Test Pass Rate % (8 runs) | 79.5% | idem |
| Regression Failures | 4 | `test_results.is_regression` |
