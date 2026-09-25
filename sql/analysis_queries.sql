-- AI workflow analytics - every query is executed by scripts/run_sql_analysis.py
-- and its result is written to docs/SQL_ANALYSIS_RESULTS.md.
-- Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

-- Q01 AI success rate, error rate and fallback rate (extraction runs)
SELECT extraction_runs, successful_runs, failed_runs, ai_success_rate_pct, error_rate_pct,
       fallback_runs, fallback_rate_pct
FROM vw_ai_quality_summary;

-- Q02 Extraction success by file type
SELECT file_family,
       COUNT(*)                                            AS runs,
       SUM(status = 'success')                             AS successful,
       ROUND(100.0 * SUM(status = 'success') / COUNT(*), 1) AS success_rate_pct,
       ROUND(AVG(processing_ms), 0)                        AS avg_processing_ms
FROM vw_extraction_runs
GROUP BY file_family
ORDER BY success_rate_pct;

-- Q03 DOCX success rate before and after the routing fix (16 Feb 2026)
SELECT CASE WHEN started_at < '2026-02-16T09:00:00' THEN '1. before fix' ELSE '2. after fix' END AS period,
       COUNT(*)                                             AS docx_runs,
       SUM(status = 'error' AND error_code = 'PARSE_ERROR') AS parse_errors,
       ROUND(100.0 * SUM(status = 'success') / COUNT(*), 1) AS success_rate_pct
FROM vw_extraction_runs
WHERE detected_format = 'docx'
GROUP BY period;

-- Q04 Field completeness and accuracy by field (weakest first)
SELECT field_name, scored, accuracy_pct, completeness_pct, missing_rate_pct, manual_corrections,
       avg_confidence_when_found
FROM vw_field_accuracy
ORDER BY accuracy_pct;

-- Q05 Average confidence by document variant, with a rank (window function)
SELECT sample_variant,
       COUNT(*)                          AS successful_runs,
       ROUND(AVG(confidence_score), 3)   AS avg_confidence,
       RANK() OVER (ORDER BY AVG(confidence_score) DESC) AS confidence_rank
FROM vw_extraction_runs
WHERE status = 'success'
GROUP BY sample_variant;

-- Q06 Is confidence a useful signal? Field accuracy by confidence band
SELECT CASE WHEN confidence_score >= 0.90 THEN '1. >= 0.90'
            WHEN confidence_score >= 0.80 THEN '2. 0.80-0.89'
            WHEN confidence_score >= 0.70 THEN '3. 0.70-0.79'
            ELSE '4. < 0.70' END                   AS confidence_band,
       COUNT(DISTINCT e.ai_run_id)                AS runs,
       ROUND(100.0 * SUM(f.is_correct) / COUNT(f.is_correct), 1) AS field_accuracy_pct,
       ROUND(100.0 * SUM(f.was_corrected) / COUNT(f.was_corrected), 1) AS manual_correction_rate_pct
FROM vw_extraction_runs e
JOIN extracted_fields f ON f.ai_run_id = e.ai_run_id
WHERE e.status = 'success'
GROUP BY confidence_band
ORDER BY confidence_band;

-- Q07 Manual correction rate by document type
SELECT file_family, sample_variant, manual_correction_rate_pct, field_accuracy_pct, human_review_rate_pct
FROM vw_document_type_performance
ORDER BY manual_correction_rate_pct DESC;

-- Q08 Error analysis: where runs fail and whether a retry recovered them
SELECT task, error_stage, error_code, detected_format, failed_runs, recovered_by_retry, first_seen, last_seen
FROM vw_error_analysis
ORDER BY failed_runs DESC;

-- Q09 Fallback: why the primary failed, and the quality of what the fallback returned
SELECT fallback_reason,
       COUNT(*)                                             AS runs,
       SUM(status = 'success')                              AS rescued_by_fallback,
       ROUND(AVG(CASE WHEN status = 'success' THEN confidence_score END), 3) AS avg_confidence
FROM vw_extraction_runs
WHERE fallback_used = 1
GROUP BY fallback_reason
ORDER BY runs DESC;

-- Q10 Provider performance
SELECT COALESCE(provider_used, 'none (both failed)') AS provider,
       COUNT(*)                                     AS runs,
       ROUND(AVG(confidence_score), 3)              AS avg_confidence,
       ROUND(AVG(processing_ms), 0)                 AS avg_processing_ms,
       ROUND(100.0 * SUM(intake_status = 'Complete') / COUNT(*), 1) AS complete_pct
FROM vw_extraction_runs
GROUP BY provider
ORDER BY runs DESC;

-- Q11 Field accuracy by provider (same documents engine vs simpler fallback)
SELECT e.provider_used, COUNT(f.is_correct) AS scored_fields,
       ROUND(100.0 * SUM(f.is_correct) / COUNT(f.is_correct), 1) AS field_accuracy_pct
FROM vw_extraction_runs e
JOIN extracted_fields f ON f.ai_run_id = e.ai_run_id
WHERE e.status = 'success'
GROUP BY e.provider_used;

-- Q12 Average processing time by format (latency model, see data dictionary)
SELECT detected_format, COUNT(*) AS runs, ROUND(AVG(processing_ms), 0) AS avg_ms,
       ROUND(MIN(processing_ms), 0) AS min_ms, ROUND(MAX(processing_ms), 0) AS max_ms
FROM vw_extraction_runs
GROUP BY detected_format
ORDER BY avg_ms;

-- Q13 Cases requiring human review, by intake status
SELECT intake_status, COUNT(*) AS cases,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
       SUM(human_review_status = 'Approved with corrections') AS corrected_by_reviewer
FROM cases
GROUP BY intake_status
ORDER BY cases DESC;

-- Q14 Missing-field frequency (successful primary extractions)
WITH missing AS (
    SELECT f.field_name, COUNT(*) AS missing_runs
    FROM extracted_fields f JOIN vw_extraction_runs e ON e.ai_run_id = f.ai_run_id
    WHERE f.is_missing = 1 AND e.status = 'success'
    GROUP BY f.field_name
)
SELECT field_name, missing_runs,
       ROUND(100.0 * missing_runs / (SELECT COUNT(*) FROM vw_extraction_runs WHERE status = 'success'), 1)
           AS missing_rate_pct,
       SUM(missing_runs) OVER (ORDER BY missing_runs DESC ROWS UNBOUNDED PRECEDING) AS cumulative_missing
FROM missing
ORDER BY missing_runs DESC;

-- Q15 Missing because the document lacks it vs missed by the extraction
SELECT f.field_name,
       SUM(f.is_missing = 1 AND f.expected_value IS NULL)     AS correctly_reported_missing,
       SUM(f.is_missing = 1 AND f.expected_value IS NOT NULL) AS missed_by_extraction
FROM extracted_fields f
GROUP BY f.field_name
HAVING SUM(f.is_missing) > 0
ORDER BY missed_by_extraction DESC;

-- Q16 Test pass rate per run and regressions
SELECT test_run_id, run_label, tests_passed || '/' || tests_total AS passed, pass_rate_pct,
       regressions, COALESCE(failed_scenarios, '-') AS failed_scenarios
FROM vw_test_run_summary
ORDER BY test_run_id;

-- Q17 Regression failures (a scenario that passed in the previous run and fails now)
SELECT t.run_label, r.scenario_code, r.scenario_name, r.failure_category, r.observed
FROM test_results r JOIN test_runs t USING (test_run_id)
WHERE r.is_regression = 1
ORDER BY t.test_run_id, r.scenario_code;

-- Q18 Scenario stability across all runs
SELECT scenario_code, scenario_name,
       SUM(status = 'PASS') || '/' || COUNT(*) AS passed_runs,
       MIN(CASE WHEN status = 'FAIL' THEN test_run_id END) AS first_failed_run,
       MAX(CASE WHEN status = 'FAIL' THEN test_run_id END) AS last_failed_run
FROM test_results
GROUP BY scenario_code, scenario_name
ORDER BY scenario_code;

-- Q19 Create Case success rate: validated intakes that became a case
SELECT COUNT(*)                                        AS successful_primary_extractions,
       SUM(case_id IS NOT NULL)                         AS turned_into_case,
       ROUND(100.0 * SUM(case_id IS NOT NULL) / COUNT(*), 1) AS create_case_success_pct
FROM vw_extraction_runs e
WHERE e.status = 'success'
  AND EXISTS (SELECT 1 FROM documents d WHERE d.document_id = e.document_id AND d.document_role = 'primary');

-- Q20 Duplicate prevention
SELECT event_type, COUNT(*) AS events
FROM audit_events
WHERE event_type IN ('duplicate_case_blocked', 'duplicate_submission_ignored', 'case_created')
GROUP BY event_type;

-- Q21 Proof that no duplicate reference exists
SELECT COUNT(*) AS cases, COUNT(DISTINCT reference_key) AS distinct_references,
       COUNT(*) - COUNT(DISTINCT reference_key) AS duplicates
FROM cases;

-- Q22 Monthly trend with running totals (window functions)
SELECT substr(started_at, 1, 7)                          AS month,
       COUNT(*)                                          AS runs,
       ROUND(100.0 * SUM(status = 'success') / COUNT(*), 1) AS success_rate_pct,
       SUM(COUNT(*)) OVER (ORDER BY substr(started_at, 1, 7)) AS cumulative_runs,
       ROUND(AVG(AVG(confidence_score)) OVER (ORDER BY substr(started_at, 1, 7)
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 3) AS confidence_3m_avg
FROM vw_extraction_runs
GROUP BY month
ORDER BY month;

-- Q23 Category corrections before and after the word-boundary fix (9 Mar 2026)
SELECT CASE WHEN e.started_at < '2026-03-09T09:00:00' THEN '1. before fix' ELSE '2. after fix' END AS period,
       COUNT(f.was_corrected)                          AS reviewed_categories,
       SUM(f.was_corrected)                            AS category_corrections
FROM extracted_fields f JOIN vw_extraction_runs e ON e.ai_run_id = f.ai_run_id
WHERE f.field_name = 'case_category'
GROUP BY period;

-- Q24 Reviewer workload and correction behaviour (simulated reviewers)
SELECT reviewer, COUNT(*) AS reviews, SUM(fields_corrected) AS fields_corrected,
       ROUND(AVG(review_seconds), 0) AS avg_review_seconds
FROM human_reviews
WHERE review_type = 'intake_validation'
GROUP BY reviewer
ORDER BY reviews DESC;

-- Q25 Product feedback generated by reviewer corrections
SELECT feedback_type, field_name, COUNT(*) AS occurrences
FROM ai_feedback
GROUP BY feedback_type, field_name
ORDER BY occurrences DESC
LIMIT 12;

-- Q26 Audit trail content check: events contain metadata only
SELECT event_type, COUNT(*) AS events, MAX(LENGTH(COALESCE(details, ''))) AS max_details_chars
FROM audit_events
GROUP BY event_type
ORDER BY events DESC;
