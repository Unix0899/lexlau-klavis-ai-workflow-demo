# DAX measures

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

42 measures, generated from `scripts/build_powerbi_project.py` (one definition produces this page, the TMDL model of the PBIP and the paste-in script `tmdl_measures_script.tmdl`).

Conventions: `DIVIDE()` everywhere; rates are ratios formatted as %; run-level quality measures (confidence, latency, fallback, human review) are computed on **extraction** runs; field measures on `FactFieldExtraction`; every definition matches the SQL views in `sql/views.sql` (see `docs/AI_QUALITY_FRAMEWORK.md`).

## AI runs

### Total AI Runs

Table `FactAIRuns` · format `#,0` · All AI runs: extraction, category suggestion, summarisation, assistant.

```DAX
Total AI Runs =
    COUNTROWS ( FactAIRuns )
```

### Successful AI Runs

Table `FactAIRuns` · format `#,0`

```DAX
Successful AI Runs =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[status] = "success" )
```

### Failed AI Runs

Table `FactAIRuns` · format `#,0` · Runs that ended in a structured error.

```DAX
Failed AI Runs =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[status] = "error" )
```

### AI Success Rate %

Table `FactAIRuns` · format `0.0%` · Successful / all AI runs in context.

```DAX
AI Success Rate % =
    DIVIDE ( [Successful AI Runs], [Total AI Runs] )
```

### Extraction Runs

Table `FactAIRuns` · format `#,0`

```DAX
Extraction Runs =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[task] = "extraction" )
```

### Successful Extractions

Table `FactAIRuns` · format `#,0`

```DAX
Successful Extractions =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[task] = "extraction", FactAIRuns[status] = "success" )
```

### Extraction Success Rate %

Table `FactAIRuns` · format `0.0%` · Document success rate: extraction runs processed without error (same as the app KPI).

```DAX
Extraction Success Rate % =
    DIVIDE ( [Successful Extractions], [Extraction Runs] )
```

### Average Confidence

Table `FactAIRuns` · format `0.00` · Mean overall confidence of successful extractions (demonstration metric).

```DAX
Average Confidence =
    CALCULATE ( AVERAGE ( FactAIRuns[confidence_score] ), FactAIRuns[task] = "extraction", FactAIRuns[status] = "success" )
```

### Average Processing Time

Table `FactAIRuns` · format `#,0` · Milliseconds. Latency of extraction runs. In the synthetic dataset it comes from a latency model (flagged per run).

```DAX
Average Processing Time =
    CALCULATE ( AVERAGE ( FactAIRuns[processing_ms] ), FactAIRuns[task] = "extraction" )
```

### Fallback Runs

Table `FactAIRuns` · format `#,0` · Extraction runs where the primary provider failed and the fallback was invoked.

```DAX
Fallback Runs =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[task] = "extraction", FactAIRuns[fallback_used] = 1 )
```

### Fallback Rate %

Table `FactAIRuns` · format `0.0%`

```DAX
Fallback Rate % =
    DIVIDE ( [Fallback Runs], [Extraction Runs] )
```

### Error Rate %

Table `FactAIRuns` · format `0.0%` · Extraction runs ended in error.

```DAX
Error Rate % =
    DIVIDE ( CALCULATE ( [Failed AI Runs], FactAIRuns[task] = "extraction" ), [Extraction Runs] )
```

### Human Review Cases

Table `FactAIRuns` · format `#,0` · Successful extractions flagged Needs Review or Missing Information.

```DAX
Human Review Cases =
    CALCULATE ( COUNTROWS ( FactAIRuns ), FactAIRuns[needs_review] = 1 )
```

### Human Review Rate %

Table `FactAIRuns` · format `0.0%`

```DAX
Human Review Rate % =
    DIVIDE ( [Human Review Cases], [Successful Extractions] )
```

### PDF Success Rate %

Table `FactAIRuns` · format `0.0%`

```DAX
PDF Success Rate % =
    CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "PDF" )
```

### DOCX Success Rate %

Table `FactAIRuns` · format `0.0%`

```DAX
DOCX Success Rate % =
    CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "DOCX" )
```

### Image Success Rate %

Table `FactAIRuns` · format `0.0%`

```DAX
Image Success Rate % =
    CALCULATE ( [Extraction Success Rate %], DimDocumentType[file_family] = "Image" )
```

## Field quality

### Scored Fields

Table `FactFieldExtraction` · format `#,0` · Fields compared with the ground truth.

```DAX
Scored Fields =
    SUM ( FactFieldExtraction[is_scored] )
```

### Correct Fields

Table `FactFieldExtraction` · format `#,0`

```DAX
Correct Fields =
    SUM ( FactFieldExtraction[is_correct] )
```

### Field Accuracy %

Table `FactFieldExtraction` · format `0.0%` · Correct fields / scored fields (null = null counts as correct).

```DAX
Field Accuracy % =
    DIVIDE ( [Correct Fields], [Scored Fields] )
```

### Completeness %

Table `FactFieldExtraction` · format `0.0%` · Share of the fields present in the document that the extraction found.

```DAX
Completeness % =
    DIVIDE ( SUM ( FactFieldExtraction[found_when_present] ), SUM ( FactFieldExtraction[expected_present] ) )
```

### Missing Fields

Table `FactFieldExtraction` · format `#,0` · Fields reported missing (absent from the document or not found).

```DAX
Missing Fields =
    SUM ( FactFieldExtraction[is_missing] )
```

### Missing Rate %

Table `FactFieldExtraction` · format `0.0%`

```DAX
Missing Rate % =
    DIVIDE ( [Missing Fields], COUNTROWS ( FactFieldExtraction ) )
```

### Conflicting Fields

Table `FactFieldExtraction` · format `#,0` · Fields with contradictory values in the document.

```DAX
Conflicting Fields =
    SUM ( FactFieldExtraction[has_conflict] )
```

### Avg Field Confidence

Table `FactFieldExtraction` · format `0.00` · Average confidence of the fields that were found.

```DAX
Avg Field Confidence =
    CALCULATE ( AVERAGE ( FactFieldExtraction[confidence] ), FactFieldExtraction[is_missing] = 0 )
```

### Manual Corrections

Table `FactFieldExtraction` · format `#,0` · Fields changed by the reviewer before the case was created.

```DAX
Manual Corrections =
    SUM ( FactFieldExtraction[was_corrected] )
```

### Manual Correction Rate %

Table `FactFieldExtraction` · format `0.0%`

```DAX
Manual Correction Rate % =
    DIVIDE ( [Manual Corrections], SUM ( FactFieldExtraction[is_reviewed] ) )
```

## Testing

### Tests Executed

Table `FactTestResults` · format `#,0`

```DAX
Tests Executed =
    COUNTROWS ( FactTestResults )
```

### Tests Passed

Table `FactTestResults` · format `#,0`

```DAX
Tests Passed =
    SUM ( FactTestResults[is_pass] )
```

### Tests Failed

Table `FactTestResults` · format `#,0`

```DAX
Tests Failed =
    SUM ( FactTestResults[is_fail] )
```

### Test Pass Rate %

Table `FactTestResults` · format `0.0%`

```DAX
Test Pass Rate % =
    DIVIDE ( [Tests Passed], [Tests Executed] )
```

### Regression Failures

Table `FactTestResults` · format `#,0` · A scenario that passed in the previous run and fails now.

```DAX
Regression Failures =
    SUM ( FactTestResults[is_regression] )
```

### Latest Test Pass Rate %

Table `FactTestResults` · format `0.0%` · Pass rate of the most recent test run (use on cards).

```DAX
Latest Test Pass Rate % =
    VAR LastRun = CALCULATE ( MAX ( FactTestResults[run_order] ), ALL ( FactTestResults ) )
    RETURN
        CALCULATE ( [Test Pass Rate %], FactTestResults[run_order] = LastRun )
```

### Test Runs

Table `FactTestResults` · format `#,0`

```DAX
Test Runs =
    DISTINCTCOUNT ( FactTestResults[test_run_id] )
```

## Human review

### Reviews

Table `FactHumanReview` · format `#,0` · Intake validations (one per created case).

```DAX
Reviews =
    CALCULATE ( COUNTROWS ( FactHumanReview ), FactHumanReview[review_type] = "intake validation" )
```

### Reviews With Corrections

Table `FactHumanReview` · format `#,0`

```DAX
Reviews With Corrections =
    CALCULATE ( [Reviews], FactHumanReview[decision] = "Approved with corrections" )
```

### Reviews With Corrections %

Table `FactHumanReview` · format `0.0%`

```DAX
Reviews With Corrections % =
    DIVIDE ( [Reviews With Corrections], [Reviews] )
```

### Avg Review Time

Table `FactHumanReview` · format `0` · Seconds. Simulated reviewers in the synthetic dataset.

```DAX
Avg Review Time =
    CALCULATE ( AVERAGE ( FactHumanReview[review_seconds] ), FactHumanReview[review_type] = "intake validation" )
```

### Category Changes

Table `FactHumanReview` · format `#,0`

```DAX
Category Changes =
    SUM ( FactHumanReview[category_changed] )
```

### Audit Events

Table `FactAuditEvents` · format `#,0`

```DAX
Audit Events =
    COUNTROWS ( FactAuditEvents )
```

### Files Rejected

Table `FactAuditEvents` · format `#,0` · Invalid or oversized uploads refused before any AI run.

```DAX
Files Rejected =
    CALCULATE ( COUNTROWS ( FactAuditEvents ), FactAuditEvents[event_type] = "file_rejected" )
```

### Duplicates Blocked

Table `FactAuditEvents` · format `#,0` · Duplicate case blocked + repeated submission ignored.

```DAX
Duplicates Blocked =
    CALCULATE ( COUNTROWS ( FactAuditEvents ), FactAuditEvents[event_group] = "Duplicate prevention" )
```
