# Architecture

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
> Independently designed demo architecture. It does not reproduce the architecture of Klavis.

```text
 DOCUMENT (PDF / DOCX / PNG / JPG)
    │  upload (≤ 5 MB)                                    app/frontend  (vanilla JS, 8 pages)
    ▼                                                          │ JSON
 INGESTION  ai/ingestion.py                                app/backend/server.py (stdlib HTTP)
    detect format from content (magic bytes)                   │
    reject: empty / too large / unsupported                    ▼
    text: pypdf │ DOCX XML │ image text layer (simulated OCR)   app/backend/services.py
    ▼                                                          │  (persistence + audit)
 AI ANALYSIS  ai/fallback.py                                    ▼
    PRIMARY  MockAIProvider ──failure──► FALLBACK  MockFallbackProvider ──failure──► STRUCTURED ERROR
    (optional: OpenAIProvider / AnthropicProvider via env)
    extraction · category suggestion · summary · assistant
    ▼
 CHECKS  ai/extraction.py
    missing fields · incomplete dates · conflicting values · confidence
    → Complete │ Needs Review │ Missing Information
    ▼
 HUMAN VALIDATION (UI)  → corrections recorded field by field
    ▼
 CASE CREATION  duplicate guard (idempotency key + unique reference)
    ▼
 SQLite  database/klavis_ai_demo.sqlite  (9 tables, 6 views, audit_events)
    ▼
 TESTS (TEST 001-014, 73 unittest tests) · SQL ANALYTICS (26 queries) · POWER BI (9-table star, 42 DAX measures)
    ▼
 PRODUCT FEEDBACK  ai_feedback · docs/BUG_INVESTIGATION_CASES.md · docs/INSIGHTS.md
```

## Components

| Layer | Files | Responsibility |
|---|---|---|
| Configuration | `ai/config.py`, `.env.example` | Limits, thresholds, provider chain, notices. No secret in code |
| Ingestion | `ai/ingestion.py` | Format detection from content, upload rules, text extraction, text-quality score |
| Provider interface | `ai/provider_interface.py` | `AIProvider` contract + output validation (a provider that breaks the contract counts as failed) |
| Providers | `ai/mock_provider.py`, `ai/external_providers.py`, `ai/registry.py` | Deterministic local engines (default); optional HTTP providers, off without a key |
| Resilience | `ai/fallback.py` | Primary → fallback → structured error, every attempt recorded |
| Workflow | `ai/extraction.py`, `ai/category_suggestion.py`, `ai/summarisation.py`, `ai/assistant.py` | Structured draft, status, summary, Q&A on the current case |
| Evaluation | `ai/evaluation.py` | Canonical comparison with the ground truth |
| Privacy | `ai/safe_logging.py` | Allow-listed, redacted, length-capped logs |
| Bug replay | `ai/bug_replay.py` | Switches that reproduce the 5 synthetic bugs (off by default) |
| Backend | `app/backend/services.py`, `app/backend/server.py` | Persistence, human validation, duplicate guard, read models, JSON API |
| Frontend | `app/frontend/` | Dashboard, New Case, AI Extraction, Cases, Case Details, AI Tests, AI Quality, Audit |
| Data | `scripts/synthetic_documents.py`, `scripts/build_dataset.py` | Documents + ground truth; six months of activity replayed through the real services |
| BI | `scripts/export_powerbi_data.py`, `scripts/build_powerbi_project.py`, `powerbi/` | Star schema, DAX, PBIP |

## API (local, JSON)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta`, `/api/health` | Notices, taxonomy, provider chain |
| GET | `/api/samples`, `/api/samples/{name}` | Synthetic sample documents |
| POST | `/api/extract` | Upload (base64) or sample → AI draft (`simulate`: `primary_down` / `all_down`) |
| GET | `/api/runs/{id}` | Draft for review |
| GET | `/api/documents/{id}/file`, `/text` | Original file / text preview (never stored, never logged) |
| POST | `/api/cases` | Create a case: requires `validated: true`; idempotency key; duplicate guard |
| GET / PATCH | `/api/cases`, `/api/cases/{id}` | List, detail, post-creation edit (recorded as a review) |
| POST | `/api/cases/{id}/summary`, `/ask` | Generate Case Summary, demo assistant |
| GET / POST | `/api/tests`, `/api/tests/run` | Test history; run TEST 001-014 now |
| GET | `/api/dashboard`, `/api/quality`, `/api/audit` | Read models of the views |

Errors are always structured: `{"status": "error", "error_code": "...", "message": "..."}` with a
meaningful HTTP status (400, 404, 409, 413, 415, 422, 503). No traceback and no document content ever
reaches the client or the log.

## Design decisions

- **AI proposes, human validates, application persists.** `create_case` refuses to run without
  `validated: true`, and every field difference between the AI draft and the validated value is stored.
- **Missing ≠ zero, unknown ≠ wrong.** A missing amount is `null` and reported. A field with no ground
  truth has `is_correct = NULL`, not 0.
- **Route on content, not on names** (the lesson of BUG-01).
- **The provider that answered is the provider recorded** (the lesson of BUG-04). Otherwise fallback
  metrics are wrong.
- **Two duplicate guards**: an idempotency key (double click, network retry) and a unique normalised
  reference (the same document uploaded again). See BUG-03.
- **Data minimisation**: the database stores metadata and structured fields, never document text.
  Summaries and the assistant receive structured fields only.
- **Standard library first**: the app runs with Python and two small packages (pypdf, Pillow).

## Simulated parts (disclosed)

| What | Why | Where it is flagged |
|---|---|---|
| OCR | No OCR engine is bundled. Generated images carry the text an OCR engine would return; degraded images carry a noisier text layer | `ai/ingestion.py`, UI label "Simulated OCR text layer" |
| AI model | Deterministic rule engine, so the demo runs without a key and is reproducible | README, Limitations |
| Latency in the dataset | The mock answers in milliseconds, so a per-format latency model is used when replaying the dataset | `ai_runs.latency_is_simulated = 1` |
| Reviewers in the dataset | The simulated reviewer corrects each field to the ground truth | `human_reviews.is_simulated = 1` |
| Provider outages | Injected at a fixed rate with the mock failure switch | `ai_runs.fallback_reason`, `error_code` |
