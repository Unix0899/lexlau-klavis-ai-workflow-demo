-- Reporting views: one definition per metric, reused by the app, the SQL analyses,
-- the Power BI exports and the tests. Definitions: docs/AI_QUALITY_FRAMEWORK.md
-- Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

-- Base: one row per extraction run, with its document.
DROP VIEW IF EXISTS vw_extraction_runs;
CREATE VIEW vw_extraction_runs AS
SELECT r.ai_run_id, r.document_id, r.case_id, r.provider_requested, r.provider_used,
       r.fallback_used, r.fallback_reason, r.status, r.error_stage, r.error_code,
       r.confidence_score, r.intake_status, r.missing_count, r.conflict_count,
       r.processing_ms, r.latency_is_simulated, r.retry_of_run_id, r.started_at,
       d.detected_format,
       CASE d.detected_format WHEN 'pdf' THEN 'PDF' WHEN 'docx' THEN 'DOCX' ELSE 'Image' END AS file_family,
       d.sample_variant, d.pages, d.text_quality
FROM ai_runs r
JOIN documents d ON d.document_id = r.document_id
WHERE r.task = 'extraction';

-- Field-level facts of successful extraction runs.
DROP VIEW IF EXISTS vw_field_facts;
CREATE VIEW vw_field_facts AS
SELECT f.field_id, f.ai_run_id, f.field_name, f.confidence, f.is_missing, f.has_conflict,
       f.is_correct, f.was_corrected,
       CASE WHEN f.expected_value IS NOT NULL THEN 1 ELSE 0 END AS expected_present,
       CASE WHEN f.expected_value IS NOT NULL AND f.ai_value IS NOT NULL THEN 1 ELSE 0 END AS found_when_present,
       e.detected_format, e.file_family, e.sample_variant, e.provider_used, e.started_at
FROM extracted_fields f
JOIN vw_extraction_runs e ON e.ai_run_id = f.ai_run_id;

-- 1. Headline AI quality (one row).
DROP VIEW IF EXISTS vw_ai_quality_summary;
CREATE VIEW vw_ai_quality_summary AS
WITH runs AS (
    SELECT COUNT(*) AS extraction_runs,
           SUM(status = 'success') AS successful_runs,
           SUM(status = 'error') AS failed_runs,
           SUM(fallback_used) AS fallback_runs,
           AVG(CASE WHEN status = 'success' THEN confidence_score END) AS avg_confidence,
           AVG(processing_ms) AS avg_processing_ms,
           SUM(status = 'success' AND intake_status <> 'Complete') AS runs_needing_review
    FROM vw_extraction_runs
), fields AS (
    SELECT SUM(is_correct) AS correct_fields,
           COUNT(is_correct) AS scored_fields,
           SUM(found_when_present) AS found_fields,
           SUM(expected_present) AS expected_fields,
           SUM(was_corrected) AS corrected_fields,
           COUNT(was_corrected) AS reviewed_fields
    FROM vw_field_facts
), tests AS (
    SELECT tests_total, tests_passed FROM test_runs ORDER BY test_run_id DESC LIMIT 1
)
SELECT r.extraction_runs, r.successful_runs, r.failed_runs,
       ROUND(100.0 * r.successful_runs / r.extraction_runs, 1)            AS ai_success_rate_pct,
       ROUND(100.0 * r.failed_runs / r.extraction_runs, 1)                AS error_rate_pct,
       r.fallback_runs,
       ROUND(100.0 * r.fallback_runs / r.extraction_runs, 1)              AS fallback_rate_pct,
       ROUND(r.avg_confidence, 3)                                         AS avg_confidence,
       ROUND(r.avg_processing_ms, 0)                                      AS avg_processing_ms,
       r.runs_needing_review,
       ROUND(100.0 * r.runs_needing_review / r.successful_runs, 1)        AS human_review_rate_pct,
       ROUND(100.0 * f.correct_fields / f.scored_fields, 1)               AS field_accuracy_pct,
       ROUND(100.0 * f.found_fields / f.expected_fields, 1)               AS completeness_pct,
       f.corrected_fields,
       ROUND(100.0 * f.corrected_fields / f.reviewed_fields, 1)           AS manual_correction_rate_pct,
       (SELECT COUNT(*) FROM cases)                                       AS cases_created,
       (SELECT ROUND(100.0 * tests_passed / tests_total, 1) FROM tests)   AS latest_test_pass_rate_pct
FROM runs r CROSS JOIN fields f;

-- 2. Performance by document type (file family x variant).
DROP VIEW IF EXISTS vw_document_type_performance;
CREATE VIEW vw_document_type_performance AS
WITH runs AS (
    SELECT file_family, detected_format, sample_variant,
           COUNT(*) AS runs, SUM(status = 'success') AS successful_runs,
           SUM(fallback_used) AS fallback_runs,
           AVG(CASE WHEN status = 'success' THEN confidence_score END) AS avg_confidence,
           AVG(processing_ms) AS avg_processing_ms,
           SUM(status = 'success' AND intake_status <> 'Complete') AS needing_review
    FROM vw_extraction_runs GROUP BY 1, 2, 3
), fields AS (
    SELECT file_family, detected_format, sample_variant,
           SUM(is_correct) AS correct, COUNT(is_correct) AS scored,
           SUM(found_when_present) AS found, SUM(expected_present) AS expected,
           SUM(was_corrected) AS corrected, COUNT(was_corrected) AS reviewed
    FROM vw_field_facts GROUP BY 1, 2, 3
)
SELECT r.file_family, r.detected_format, r.sample_variant, r.runs, r.successful_runs,
       ROUND(100.0 * r.successful_runs / r.runs, 1)     AS success_rate_pct,
       ROUND(100.0 * r.fallback_runs / r.runs, 1)       AS fallback_rate_pct,
       ROUND(r.avg_confidence, 3)                       AS avg_confidence,
       ROUND(r.avg_processing_ms, 0)                    AS avg_processing_ms,
       ROUND(100.0 * f.correct / f.scored, 1)           AS field_accuracy_pct,
       ROUND(100.0 * f.found / f.expected, 1)           AS completeness_pct,
       ROUND(100.0 * f.corrected / f.reviewed, 1)       AS manual_correction_rate_pct,
       ROUND(100.0 * r.needing_review / r.successful_runs, 1) AS human_review_rate_pct
FROM runs r
LEFT JOIN fields f USING (file_family, detected_format, sample_variant);

-- 3. Accuracy by extracted field.
DROP VIEW IF EXISTS vw_field_accuracy;
CREATE VIEW vw_field_accuracy AS
SELECT field_name,
       COUNT(*)                                             AS extractions,
       COUNT(is_correct)                                    AS scored,
       SUM(is_correct)                                      AS correct,
       ROUND(100.0 * SUM(is_correct) / COUNT(is_correct), 1) AS accuracy_pct,
       ROUND(100.0 * SUM(found_when_present) / NULLIF(SUM(expected_present), 0), 1) AS completeness_pct,
       ROUND(100.0 * SUM(is_missing) / COUNT(*), 1)         AS missing_rate_pct,
       SUM(has_conflict)                                    AS conflicts,
       SUM(was_corrected)                                   AS manual_corrections,
       ROUND(100.0 * SUM(was_corrected) / NULLIF(COUNT(was_corrected), 0), 1) AS correction_rate_pct,
       ROUND(AVG(CASE WHEN is_missing = 0 THEN confidence END), 3) AS avg_confidence_when_found
FROM vw_field_facts
GROUP BY field_name;

-- 4. Test runs: pass rate and regressions.
DROP VIEW IF EXISTS vw_test_run_summary;
CREATE VIEW vw_test_run_summary AS
SELECT t.test_run_id, t.run_label, t.code_version, COALESCE(t.bug_replay, '') AS bug_replay,
       t.trigger, t.started_at, t.tests_total, t.tests_passed, t.tests_failed,
       ROUND(100.0 * t.tests_passed / t.tests_total, 1) AS pass_rate_pct,
       (SELECT COUNT(*) FROM test_results r WHERE r.test_run_id = t.test_run_id
                                              AND r.is_regression = 1) AS regressions,
       (SELECT GROUP_CONCAT(scenario_code, ', ') FROM test_results r
         WHERE r.test_run_id = t.test_run_id AND r.status = 'FAIL') AS failed_scenarios
FROM test_runs t;

-- 5. Human review, by month of review.
DROP VIEW IF EXISTS vw_human_review_metrics;
CREATE VIEW vw_human_review_metrics AS
SELECT substr(h.reviewed_at, 1, 7)                          AS review_month,
       COUNT(*)                                             AS reviews,
       SUM(h.decision = 'Approved with corrections')        AS reviews_with_corrections,
       ROUND(100.0 * SUM(h.decision = 'Approved with corrections') / COUNT(*), 1) AS reviews_with_corrections_pct,
       SUM(h.fields_reviewed)                               AS fields_reviewed,
       SUM(h.fields_corrected)                              AS fields_corrected,
       ROUND(100.0 * SUM(h.fields_corrected) / SUM(h.fields_reviewed), 1) AS field_correction_rate_pct,
       SUM(h.category_changed)                              AS category_changes,
       ROUND(AVG(h.review_seconds), 0)                      AS avg_review_seconds,
       SUM(c.intake_status <> 'Complete')                   AS cases_needing_review
FROM human_reviews h
JOIN cases c ON c.case_id = h.case_id
WHERE h.review_type = 'intake_validation'
GROUP BY 1;

-- 6. Errors: where and why runs fail.
DROP VIEW IF EXISTS vw_error_analysis;
CREATE VIEW vw_error_analysis AS
SELECT r.task,
       COALESCE(r.error_stage, 'ai_provider')               AS error_stage,
       r.error_code,
       COALESCE(d.detected_format, 'unknown')               AS detected_format,
       COUNT(*)                                             AS failed_runs,
       SUM(EXISTS (SELECT 1 FROM ai_runs x WHERE x.retry_of_run_id = r.ai_run_id
                                              AND x.status = 'success')) AS recovered_by_retry,
       MIN(r.started_at)                                    AS first_seen,
       MAX(r.started_at)                                    AS last_seen
FROM ai_runs r
JOIN documents d ON d.document_id = r.document_id
WHERE r.status = 'error'
GROUP BY 1, 2, 3, 4;
