# Data dictionary

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Database: `database/klavis_ai_demo.sqlite`. Schema: `sql/schema.sql`. Views: `sql/views.sql`.
Full dump: `sql/full_database_dump.sql`.

| Table | Rows | Grain |
|---|---:|---|
| cases | 260 | one validated case |
| documents | 357 | one uploaded file (incl. 8 rejected uploads, 12 re-uploads, 50 supporting documents, 27 re-submissions after a failure) |
| ai_runs | 892 | one AI call chain: 349 extractions, 320 category suggestions, 133 summaries, 90 assistant answers |
| extracted_fields | 2,880 | one field of one successful extraction (9 per run) |
| human_reviews | 353 | one review: 260 intake validations + 93 post-creation edits |
| ai_feedback | 150 | one reviewer correction turned into product feedback |
| test_runs | 8 | one execution of the TEST 001-014 suite |
| test_results | 112 | one scenario in one run |
| audit_events | 1,603 | one workflow event (metadata only) |

## cases

| Column | Type | Rule / meaning |
|---|---|---|
| case_id | int PK | |
| case_reference | text | as validated (`SYN-26-00042`) |
| reference_key | text UNIQUE | normalised reference (alphanumerics, upper case): the duplicate guard |
| title, client_name, opposing_party, jurisdiction, document_type | text | validated values (opposing party / jurisdiction may stay empty when missing) |
| category | text CHECK | taxonomy: Commercial dispute, Contract dispute, Employment matter, Corporate matter, Administrative matter, Other |
| important_dates, amounts, missing_fields | JSON text | validated lists |
| summary | text | last generated summary (AI draft) |
| status | CHECK | Open, Awaiting information (required info still missing), Closed |
| intake_status | CHECK | status of the AI draft: Complete, Needs Review, Missing Information |
| source_document_id, source_ai_run_id | FK | the document and extraction the case came from |
| ai_confidence | real 0-1 | overall confidence of the draft |
| human_review_status | CHECK | Approved / Approved with corrections |
| idempotency_key | text UNIQUE | one key per submission: a repeated request returns the existing case |
| created_by, created_at, updated_at | | `updated_at >= created_at` |

## documents

| Column | Meaning |
|---|---|
| detected_format | pdf, docx, png, jpg (from content). NULL for rejected uploads |
| sample_variant | clean, degraded, multipage, missing_fields, contradictory (synthetic generator), upload (demo), invalid / oversized |
| document_role | primary (creates the case) or supporting (attached later) |
| byte_size, pages, sha256, text_quality | metadata. `text_quality` = share of clean tokens (OCR noise proxy) |
| ingestion_status, rejection_code | accepted / rejected (+ EMPTY_FILE, FILE_TOO_LARGE, UNSUPPORTED_FORMAT) |
| storage_path | where the file is. **No document text is stored** |

## ai_runs

| Column | Meaning |
|---|---|
| task | extraction, category_suggestion, summarisation, assistant |
| provider_requested / provider_used | first provider of the chain / provider whose answer was kept (NULL if all failed) |
| fallback_used, fallback_reason | 1 when the primary failed; reason = its error code (PROVIDER_TIMEOUT, PROVIDER_ERROR, INVALID_OUTPUT) |
| status, error_stage, error_code | success / error; stage `text_extraction` (PARSE_ERROR, NO_TEXT_FOUND) or `ai_provider` (AI_UNAVAILABLE) |
| confidence_score | mean of the 9 field confidences (0 for missing fields) |
| intake_status, missing_count, conflict_count | result of the checks |
| processing_ms, latency_is_simulated | measured time (live demo) or latency model (dataset replay, flag = 1) |
| retry_of_run_id | the failed run this re-submission recovers |
| bug_replay | replay switches active at run time (dataset: `docx_routing` until 16/02/2026, `category_substring` until 09/03/2026) |

## extracted_fields

| Column | Meaning |
|---|---|
| field_name | case_title, case_reference, client_name, opposing_party, document_type, jurisdiction, important_dates, amounts, case_category |
| ai_value | AI proposal (JSON text for dates and amounts) |
| confidence, method | label (0.95), ocr_tolerant_label (0.72), gazetteer (0.68), heading, keyword_taxonomy, scaled by text quality |
| is_missing, has_conflict | flags raised by the checks |
| expected_value, is_correct | ground truth and comparison (synthetic dataset only; NULL = unknown, not wrong) |
| final_value, was_corrected, review_id | validated value and whether the human changed it |

## Other tables

- **human_reviews**: reviewer (pseudonymous id), review_type, decision, fields_reviewed / corrected,
  category_changed, review_seconds, is_simulated. `CHECK (decision = 'Approved') = (fields_corrected = 0)`.
- **ai_feedback**: feedback_type (wrong_value, missing_value, format_issue, wrong_category,
  conflict_resolved, false_positive) from a fixed vocabulary: no free text.
- **test_runs / test_results**: label, version, bug_replay, totals (`passed + failed = total`); per
  scenario: expected, observed, PASS / FAIL, failure_category, is_regression (passed in the previous
  run, fails now).
- **audit_events**: event_type, actor, entity, format, processing status, provider, latency, error
  code, allow-listed details. See `docs/DATA_PRIVACY.md`.

## Views

| View | Question |
|---|---|
| vw_extraction_runs, vw_field_facts | base views (one row per extraction run / per field) |
| vw_ai_quality_summary | headline KPIs |
| vw_document_type_performance | quality by file family × variant |
| vw_field_accuracy | accuracy, completeness, missing rate, corrections by field |
| vw_test_run_summary | pass rate, regressions, failed scenarios by run |
| vw_human_review_metrics | reviews and corrections by month |
| vw_error_analysis | failures by task, stage, code, format, and whether a retry recovered them |

## CSV exports

| File | Content |
|---|---|
| `data/synthetic_cases.csv` | 260 cases + source document format / variant |
| `data/synthetic_ai_runs.csv` | 892 AI runs + document format / variant / role |
| `data/synthetic_test_results.csv` | 112 results of the 8 test runs |
| `data/ground_truth.json` | expected values of the 310 generated documents + 9 samples |
| `powerbi/data/*.csv` | star schema for Power BI (see `powerbi/DATA_MODEL.md`) |
