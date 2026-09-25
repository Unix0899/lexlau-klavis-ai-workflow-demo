# Data protection

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Legal documents are among the most sensitive documents there are. This demo applies the protections a
legal AI workflow needs, on data that is fully synthetic.

| Principle | How it is applied | Evidence |
|---|---|---|
| **Synthetic data** | Every person, company, municipality, reference, amount and document is generated; every document carries the banner "SYNTHETIC DEMONSTRATION DOCUMENT - FICTIONAL DATA" | `scripts/synthetic_documents.py`, `data/ground_truth.json` |
| **No production data** | No LexLau/Klavis document, case, database, log or test report was used or copied | `docs/AUDIT_EXISTANT.md` |
| **No secrets** | No key in code or data. `.env.example` only; `.env` is git-ignored. External providers are off without a key and are never called by tests | `.env.example`, `docs/SECURITY_SCAN.md` (0 blocking findings) |
| **Data minimisation** | The database stores metadata and structured fields, **never the document text**. Summaries and the assistant receive only the structured fields. Assistant questions are not stored | `tests/integration/test_workflow_db.py::test_no_document_text_in_database_or_log`, `test_summary_and_assistant_runs_recorded_without_question_text` |
| **Controlled logging** | Allow-list of keys (anything else is dropped and counted), redaction of e-mail / phone / IBAN / national-number patterns, 80-character cap, lists and objects omitted | `ai/safe_logging.py`, `tests/unit/test_safe_logging.py` |
| **Redacted documents** | The text preview is served to the reviewer's screen only; the file itself is served only from the two allowed folders | `app/backend/server.py::_document` |
| **Human review** | No case without explicit validation. Every correction is recorded per field | `create_case(..., validated=True)`, `human_reviews`, `extracted_fields.was_corrected` |
| **Auditability** | 1,603 audit events: uploads, rejections, AI runs, fallbacks, reviews, case creation, duplicates, summaries, questions, test runs. Metadata only | `audit_events`, Audit page, `proofs/proof_08_audit_log.png` |
| **Retention awareness** | Uploaded demo files live in `app_uploads/` (git-ignored); the runtime database is a disposable copy (`database/app_runtime.sqlite`). Deleting both resets the demo. A real system needs a retention period per document type, set with the data controller | `.gitignore`, README "How to run" |
| **Environment separation** | Reference dataset (read-only in analyses) ≠ runtime database ≠ test databases (temporary, one per scenario) | `services.ensure_runtime_db`, `tests/e2e/scenarios.py::fresh_db` |
| **Pseudonymous actors** | Reviewers and users are ids (`reviewer_02`, `user_05`), not names | `human_reviews.reviewer` |

## What is logged

```json
{"ts": "2026-09-24T18:08:12+00:00", "event_type": "ai_extraction_completed", "actor": "demo_user",
 "entity_type": "ai_run", "entity_id": 900, "document_id": 363, "format": "jpg",
 "processing_status": "success", "provider": "mock-primary", "latency_ms": 6.2,
 "confidence_score": 0.707, "case_status": "Missing Information", "missing_count": 3, "conflict_count": 0}
```

Logged: document id, format, processing status, latency, provider, error code, counts.
**Never logged**: full document content, extracted values (names, amounts), client secrets, question
text, unnecessary personal data. A test writes a canary paragraph through the workflow and checks it is
absent from the database dump and the log file.

## If an external provider is switched on

Setting `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` sends the (truncated) document text to that provider for
extraction. That is acceptable for the synthetic documents of this repository and **not** for real
client documents without a data processing agreement, a legal basis and a data-protection review. The
default configuration never sends anything anywhere.
