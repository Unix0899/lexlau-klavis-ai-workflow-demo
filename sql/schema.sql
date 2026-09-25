-- Klavis AI Workflow Demo - relational schema (SQLite)
-- Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
-- Independently designed for this public demo; it is not the schema of the Klavis platform.
--
--   cases 1--N documents 1--N ai_runs 1--N extracted_fields
--   cases 1--N human_reviews          ai_runs 1--N ai_feedback
--   test_runs 1--N test_results       audit_events (metadata only, no document content)
--
-- The database stores metadata and structured fields, never the full text of a document.

PRAGMA foreign_keys = ON;

CREATE TABLE documents (
    document_id        INTEGER PRIMARY KEY,
    case_id            INTEGER REFERENCES cases(case_id),           -- NULL until a case is created
    filename           TEXT    NOT NULL,
    declared_extension TEXT,
    detected_format    TEXT CHECK (detected_format IN ('pdf', 'docx', 'png', 'jpg')),
    sample_variant     TEXT CHECK (sample_variant IN ('clean', 'degraded', 'multipage',
                                   'missing_fields', 'contradictory', 'invalid', 'oversized', 'upload')),
    document_role      TEXT NOT NULL DEFAULT 'primary' CHECK (document_role IN ('primary', 'supporting')),
    byte_size          INTEGER NOT NULL CHECK (byte_size >= 0),
    pages              INTEGER CHECK (pages IS NULL OR pages >= 1),
    sha256             TEXT    NOT NULL,
    text_quality       REAL CHECK (text_quality IS NULL OR text_quality BETWEEN 0 AND 1),
    ingestion_status   TEXT NOT NULL CHECK (ingestion_status IN ('accepted', 'rejected')),
    rejection_code     TEXT,
    storage_path       TEXT,                                          -- file on disk, never the text
    uploaded_by        TEXT NOT NULL,
    uploaded_at        TEXT NOT NULL,
    CHECK (ingestion_status = 'accepted' OR rejection_code IS NOT NULL),
    CHECK (ingestion_status = 'rejected' OR detected_format IS NOT NULL)
);

CREATE TABLE ai_runs (
    ai_run_id            INTEGER PRIMARY KEY,
    document_id          INTEGER NOT NULL REFERENCES documents(document_id),
    case_id              INTEGER REFERENCES cases(case_id),
    task                 TEXT NOT NULL CHECK (task IN ('extraction', 'category_suggestion',
                                                       'summarisation', 'assistant')),
    provider_requested   TEXT NOT NULL,
    provider_used        TEXT,
    fallback_used        INTEGER NOT NULL DEFAULT 0 CHECK (fallback_used IN (0, 1)),
    fallback_reason      TEXT,
    status               TEXT NOT NULL CHECK (status IN ('success', 'error')),
    error_stage          TEXT CHECK (error_stage IN ('text_extraction', 'ai_provider')),
    error_code           TEXT,
    confidence_score     REAL CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
    intake_status        TEXT CHECK (intake_status IN ('Complete', 'Needs Review', 'Missing Information')),
    missing_count        INTEGER CHECK (missing_count IS NULL OR missing_count >= 0),
    conflict_count       INTEGER CHECK (conflict_count IS NULL OR conflict_count >= 0),
    processing_ms        REAL NOT NULL CHECK (processing_ms >= 0),
    latency_is_simulated INTEGER NOT NULL DEFAULT 0 CHECK (latency_is_simulated IN (0, 1)),
    retry_of_run_id      INTEGER REFERENCES ai_runs(ai_run_id),
    bug_replay           TEXT,                                         -- replay switches active, if any
    started_at           TEXT NOT NULL,
    CHECK (status = 'success' OR error_code IS NOT NULL),
    CHECK (status = 'error' OR provider_used IS NOT NULL),
    CHECK (fallback_used = 0 OR fallback_reason IS NOT NULL)
);

CREATE TABLE cases (
    case_id             INTEGER PRIMARY KEY,
    case_reference      TEXT NOT NULL,
    reference_key       TEXT UNIQUE,                                   -- normalised reference: duplicate guard
    title               TEXT NOT NULL,
    client_name         TEXT NOT NULL,
    opposing_party      TEXT,
    category            TEXT NOT NULL CHECK (category IN ('Commercial dispute', 'Contract dispute',
                             'Employment matter', 'Corporate matter', 'Administrative matter', 'Other')),
    jurisdiction        TEXT,
    document_type       TEXT,
    important_dates     TEXT,                                          -- JSON list
    amounts             TEXT,                                          -- JSON list
    missing_fields      TEXT,                                          -- JSON list
    summary             TEXT,
    status              TEXT NOT NULL CHECK (status IN ('Open', 'Awaiting information', 'Closed')),
    intake_status       TEXT NOT NULL CHECK (intake_status IN ('Complete', 'Needs Review',
                                                               'Missing Information')),
    source_document_id  INTEGER NOT NULL REFERENCES documents(document_id),
    source_ai_run_id    INTEGER NOT NULL REFERENCES ai_runs(ai_run_id),
    ai_confidence       REAL CHECK (ai_confidence BETWEEN 0 AND 1),
    human_review_status TEXT NOT NULL CHECK (human_review_status IN ('Approved',
                                                                     'Approved with corrections')),
    idempotency_key     TEXT UNIQUE,
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK (updated_at >= created_at)
);

CREATE TABLE extracted_fields (
    field_id       INTEGER PRIMARY KEY,
    ai_run_id      INTEGER NOT NULL REFERENCES ai_runs(ai_run_id),
    field_name     TEXT NOT NULL CHECK (field_name IN ('case_title', 'case_reference', 'client_name',
                        'opposing_party', 'document_type', 'jurisdiction', 'important_dates',
                        'amounts', 'case_category')),
    ai_value       TEXT,                                               -- JSON text for list fields
    confidence     REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    method         TEXT,
    is_missing     INTEGER NOT NULL CHECK (is_missing IN (0, 1)),
    has_conflict   INTEGER NOT NULL DEFAULT 0 CHECK (has_conflict IN (0, 1)),
    expected_value TEXT,                                               -- ground truth (synthetic set only)
    is_correct     INTEGER CHECK (is_correct IN (0, 1)),               -- NULL = no ground truth
    final_value    TEXT,                                               -- value after human review
    was_corrected  INTEGER CHECK (was_corrected IN (0, 1)),            -- NULL = not reviewed yet
    review_id      INTEGER REFERENCES human_reviews(review_id),
    UNIQUE (ai_run_id, field_name),
    CHECK (is_missing = 0 OR ai_value IS NULL)
);

CREATE TABLE human_reviews (
    review_id        INTEGER PRIMARY KEY,
    case_id          INTEGER NOT NULL REFERENCES cases(case_id),
    ai_run_id        INTEGER NOT NULL REFERENCES ai_runs(ai_run_id),
    reviewer         TEXT NOT NULL,                                    -- pseudonymous id
    review_type      TEXT NOT NULL CHECK (review_type IN ('intake_validation', 'post_creation_edit')),
    decision         TEXT NOT NULL CHECK (decision IN ('Approved', 'Approved with corrections')),
    fields_reviewed  INTEGER NOT NULL CHECK (fields_reviewed >= 0),
    fields_corrected INTEGER NOT NULL CHECK (fields_corrected >= 0),
    category_changed INTEGER NOT NULL DEFAULT 0 CHECK (category_changed IN (0, 1)),
    review_seconds   INTEGER CHECK (review_seconds IS NULL OR review_seconds >= 0),
    is_simulated     INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
    reviewed_at      TEXT NOT NULL,
    CHECK (fields_corrected <= fields_reviewed),
    CHECK ((decision = 'Approved') = (fields_corrected = 0))
);

CREATE TABLE ai_feedback (
    feedback_id   INTEGER PRIMARY KEY,
    ai_run_id     INTEGER NOT NULL REFERENCES ai_runs(ai_run_id),
    case_id       INTEGER REFERENCES cases(case_id),
    field_name    TEXT NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('wrong_value', 'missing_value', 'format_issue',
                                       'wrong_category', 'conflict_resolved', 'false_positive')),
    comment       TEXT,                                                -- fixed vocabulary, no free text
    created_at    TEXT NOT NULL
);

CREATE TABLE test_runs (
    test_run_id  INTEGER PRIMARY KEY,
    run_label    TEXT NOT NULL,
    code_version TEXT NOT NULL,
    bug_replay   TEXT,
    trigger      TEXT NOT NULL CHECK (trigger IN ('ci', 'manual', 'ui')),
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL,
    tests_total  INTEGER NOT NULL CHECK (tests_total >= 0),
    tests_passed INTEGER NOT NULL CHECK (tests_passed >= 0),
    tests_failed INTEGER NOT NULL CHECK (tests_failed >= 0),
    CHECK (tests_passed + tests_failed = tests_total),
    CHECK (finished_at >= started_at)
);

CREATE TABLE test_results (
    result_id        INTEGER PRIMARY KEY,
    test_run_id      INTEGER NOT NULL REFERENCES test_runs(test_run_id),
    scenario_code    TEXT NOT NULL CHECK (scenario_code GLOB 'TEST [0-9][0-9][0-9]'),
    scenario_name    TEXT NOT NULL,
    document_format  TEXT,
    expected         TEXT NOT NULL,
    observed         TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    failure_category TEXT,
    is_regression    INTEGER NOT NULL DEFAULT 0 CHECK (is_regression IN (0, 1)),
    duration_ms      REAL NOT NULL CHECK (duration_ms >= 0),
    UNIQUE (test_run_id, scenario_code),
    CHECK (status = 'PASS' OR failure_category IS NOT NULL)
);

CREATE TABLE audit_events (
    event_id          INTEGER PRIMARY KEY,
    event_time        TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    actor             TEXT NOT NULL,
    entity_type       TEXT,
    entity_id         INTEGER,
    document_id       INTEGER,
    format            TEXT,
    processing_status TEXT,
    provider          TEXT,
    latency_ms        REAL,
    error_code        TEXT,
    details           TEXT                                             -- allow-listed metadata (JSON)
);

CREATE INDEX ix_documents_case ON documents(case_id);
CREATE INDEX ix_documents_sha ON documents(sha256);
CREATE INDEX ix_ai_runs_document ON ai_runs(document_id);
CREATE INDEX ix_ai_runs_case ON ai_runs(case_id);
CREATE INDEX ix_ai_runs_task_status ON ai_runs(task, status);
CREATE INDEX ix_fields_run ON extracted_fields(ai_run_id);
CREATE INDEX ix_reviews_case ON human_reviews(case_id);
CREATE INDEX ix_results_run ON test_results(test_run_id);
CREATE INDEX ix_audit_time ON audit_events(event_time);
