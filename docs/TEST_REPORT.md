# Test report

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Run on 25/09/2026 09:54 with `python scripts/run_tests.py` (Python 3.14.6, standard `unittest`, 28.8 s).

| Level | Passed | Failed |
|---|---:|---:|
| e2e | 10 | 0 |
| integration | 21 | 0 |
| unit | 42 | 0 |
| **Total** | **73** | **0** |

TEST 001 - TEST 014 are executed inside `tests/e2e/test_scenarios.py` (all 14 as sub-tests, plus one check per replayed synthetic bug).

## Tests

| Test | Result | ms |
|---|---|---:|
| `e2e.test_http_api.HttpApi.test_fallback_and_outage_over_http` | PASS | 620 |
| `e2e.test_http_api.HttpApi.test_frontend_shows_disclosure` | PASS | 221 |
| `e2e.test_http_api.HttpApi.test_full_workflow_over_http` | PASS | 192 |
| `e2e.test_http_api.HttpApi.test_invalid_and_oversized_uploads` | PASS | 231 |
| `e2e.test_http_api.HttpApi.test_invalid_category_rejected` | PASS | 4 |
| `e2e.test_http_api.HttpApi.test_meta_notices` | PASS | 3 |
| `e2e.test_http_api.HttpApi.test_request_log_is_metadata_only` | PASS | 53 |
| `e2e.test_http_api.HttpApi.test_unknown_endpoint_and_errors_are_structured` | PASS | 25 |
| `e2e.test_scenarios.ScenarioSuite.test_all_scenarios_pass` | PASS | 3860 |
| `e2e.test_scenarios.ScenarioSuite.test_each_synthetic_bug_is_detected` | PASS | 19690 |
| `integration.test_reference_dataset.ReferenceDataset.test_all_views_return_rows` | PASS | 36 |
| `integration.test_reference_dataset.ReferenceDataset.test_audit_has_no_document_text` | PASS | 3 |
| `integration.test_reference_dataset.ReferenceDataset.test_csv_exports_match_database` | PASS | 76 |
| `integration.test_reference_dataset.ReferenceDataset.test_every_case_was_human_validated` | PASS | 1 |
| `integration.test_reference_dataset.ReferenceDataset.test_ground_truth_matches_documents_on_disk` | PASS | 70 |
| `integration.test_reference_dataset.ReferenceDataset.test_integrity_and_foreign_keys` | PASS | 18 |
| `integration.test_reference_dataset.ReferenceDataset.test_latest_test_run_is_green` | PASS | 0 |
| `integration.test_reference_dataset.ReferenceDataset.test_no_duplicate_case_reference` | PASS | 1 |
| `integration.test_reference_dataset.ReferenceDataset.test_simulated_parts_are_flagged` | PASS | 1 |
| `integration.test_reference_dataset.ReferenceDataset.test_volumes_within_spec` | PASS | 1 |
| `integration.test_workflow_db.WorkflowTest.test_case_requires_explicit_validation` | PASS | 243 |
| `integration.test_workflow_db.WorkflowTest.test_create_case_links_everything` | PASS | 260 |
| `integration.test_workflow_db.WorkflowTest.test_failed_run_is_recorded_and_not_reviewable` | PASS | 231 |
| `integration.test_workflow_db.WorkflowTest.test_missing_information_case_awaits_information` | PASS | 306 |
| `integration.test_workflow_db.WorkflowTest.test_no_document_text_in_database_or_log` | PASS | 291 |
| `integration.test_workflow_db.WorkflowTest.test_post_creation_edit_is_a_review` | PASS | 268 |
| `integration.test_workflow_db.WorkflowTest.test_rejected_upload_starts_no_ai_run` | PASS | 199 |
| `integration.test_workflow_db.WorkflowTest.test_required_fields_enforced` | PASS | 295 |
| `integration.test_workflow_db.WorkflowTest.test_schema_constraints` | PASS | 217 |
| `integration.test_workflow_db.WorkflowTest.test_summary_and_assistant_runs_recorded_without_question_text` | PASS | 250 |
| `integration.test_workflow_db.WorkflowTest.test_upload_persists_document_run_and_fields` | PASS | 241 |
| `unit.test_ai_services.Category.test_no_keyword_is_other_with_low_confidence` | PASS | 1 |
| `unit.test_ai_services.Category.test_taxonomy` | PASS | 1 |
| `unit.test_ai_services.Category.test_word_boundary_and_bug02_replay` | PASS | 1 |
| `unit.test_ai_services.ExternalProviders.test_no_key_means_unavailable_then_mock_fallback` | PASS | 22 |
| `unit.test_ai_services.ExternalProviders.test_no_network_call_without_key` | PASS | 6 |
| `unit.test_ai_services.Fallback.test_bug04_replay_mislabels_provider` | PASS | 1 |
| `unit.test_ai_services.Fallback.test_contract_validation` | PASS | 0 |
| `unit.test_ai_services.Fallback.test_each_failure_type_falls_back` | PASS | 2 |
| `unit.test_ai_services.Fallback.test_primary_success` | PASS | 1 |
| `unit.test_ai_services.Fallback.test_structured_error_when_all_fail` | PASS | 0 |
| `unit.test_ai_services.SummaryAndAssistant.test_assistant_answers_and_refuses_advice` | PASS | 0 |
| `unit.test_ai_services.SummaryAndAssistant.test_empty_question` | PASS | 0 |
| `unit.test_ai_services.SummaryAndAssistant.test_summary_has_notice_and_uses_structured_fields` | PASS | 0 |
| `unit.test_ingestion.DetectFormat.test_magic_bytes` | PASS | 2 |
| `unit.test_ingestion.DetectFormat.test_unknown_bytes` | PASS | 0 |
| `unit.test_ingestion.DetectFormat.test_zip_that_is_not_docx` | PASS | 1 |
| `unit.test_ingestion.Ingest.test_bug01_replay_routes_docx_to_pdf_parser` | PASS | 2 |
| `unit.test_ingestion.Ingest.test_corrupted_pdf_is_parse_error_not_crash` | PASS | 0 |
| `unit.test_ingestion.Ingest.test_docx_text` | PASS | 1 |
| `unit.test_ingestion.Ingest.test_extension_mismatch_is_a_warning` | PASS | 8 |
| `unit.test_ingestion.Ingest.test_image_simulated_ocr_layer` | PASS | 3 |
| `unit.test_ingestion.Ingest.test_image_without_text_layer_is_a_controlled_error` | PASS | 1 |
| `unit.test_ingestion.Ingest.test_pdf_text_and_pages` | PASS | 11 |
| `unit.test_ingestion.Ingest.test_rejections` | PASS | 9 |
| `unit.test_ingestion.Ingest.test_text_quality` | PASS | 0 |
| `unit.test_normalisation.Amounts.test_formats` | PASS | 0 |
| `unit.test_normalisation.Amounts.test_small_and_missing` | PASS | 0 |
| `unit.test_normalisation.Dates.test_formats` | PASS | 0 |
| `unit.test_normalisation.Dates.test_incomplete_and_invalid` | PASS | 0 |
| `unit.test_normalisation.Evaluation.test_lists_ignore_order_and_raw` | PASS | 0 |
| `unit.test_normalisation.Evaluation.test_null_equals_null` | PASS | 0 |
| `unit.test_normalisation.Evaluation.test_text_normalisation` | PASS | 0 |
| `unit.test_normalisation.MockExtraction.test_conflict_detected` | PASS | 1 |
| `unit.test_normalisation.MockExtraction.test_fallback_engine_is_stricter` | PASS | 1 |
| `unit.test_normalisation.MockExtraction.test_gazetteer_when_no_label` | PASS | 1 |
| `unit.test_normalisation.MockExtraction.test_label_variants` | PASS | 1 |
| `unit.test_normalisation.MockExtraction.test_missing_amount_is_null_not_zero` | PASS | 2 |
| `unit.test_normalisation.MockExtraction.test_ocr_tolerant_labels_and_reference` | PASS | 1 |
| `unit.test_safe_logging.Redaction.test_allow_list_drops_content_keys` | PASS | 0 |
| `unit.test_safe_logging.Redaction.test_log_file_contains_metadata_only` | PASS | 25 |
| `unit.test_safe_logging.Redaction.test_long_values_truncated_and_structures_omitted` | PASS | 5 |
| `unit.test_safe_logging.Redaction.test_patterns` | PASS | 0 |
