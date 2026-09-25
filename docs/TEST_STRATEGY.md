# Test strategy

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Testing an AI workflow means testing the **whole path**: the file, the text, the model answer, the checks,
the human step, the database, the failure modes and the logs, not only "does the model answer".

```bash
python scripts/run_tests.py          # 73 tests: unit + integration + e2e, writes docs/TEST_REPORT.md
python -m unittest discover -s tests -t .
```

## Levels

| Level | Folder | Tests | What it proves |
|---|---|---:|---|
| Unit | `tests/unit` | 42 | format detection, upload rules, parsers, date / amount normalisation, OCR-tolerant labels, conflicts, missing ≠ 0, category taxonomy, fallback chain, contract validation, external providers without key, summary / assistant notices, log redaction |
| Integration | `tests/integration` | 21 | workflow + database: nothing becomes a case without validation, required fields, links, post-creation edits, failed runs, rejected uploads, **no document text in DB or logs**, schema constraints; published dataset integrity, volumes, views, ground truth, CSV exports |
| End-to-end | `tests/e2e` | 10 | TEST 001-014 on the real workflow; each replayed bug is caught; the real HTTP server (upload → draft → validation → case → duplicate → summary → assistant; fallback and outage; invalid / oversized uploads; structured errors; request log without query strings) |
| Fixtures | `tests/fixtures` | 14 files | synthetic documents with expected values (`expected.json`), invalid file, renamed executable |

Counts are test methods (73 in total); TEST 001-014 run as 14 sub-tests inside one e2e method. The full list with durations is in `docs/TEST_REPORT.md`.

## Scenario suite TEST 001-014

Each scenario runs on a fresh temporary database (`tests/e2e/scenarios.py`).

| Code | Scenario | Expected | Guards against |
|---|---|---|---|
| TEST 001 | Clean PDF | all required fields extracted (9/9 = ground truth) | extraction accuracy |
| TEST 002 | DOCX | text correctly extracted, 9/9 fields | document routing (BUG-01) |
| TEST 003 | Clean image | OCR / vision processing succeeds, status Complete | image path |
| TEST 004 | Degraded image | lower confidence than the clean image, not *Complete*, no crash | robustness |
| TEST 005 | Missing field | jurisdiction and amount in `missing_fields`, null not 0 | BUG-05 |
| TEST 006 | Multiple dates | 4 dates in 4 formats → 4 labelled ISO dates | date normalisation |
| TEST 007 | Provider failure | fallback invoked **and recorded** (provider, flag, reason) | BUG-04 |
| TEST 008 | Both providers fail | `AI_UNAVAILABLE`, message, 2 attempts, no case | error handling |
| TEST 009 | Duplicate submission | double click + re-upload → exactly 1 case | BUG-03 |
| TEST 010 | Human correction | corrected values persisted in case, field, review and feedback | human-in-the-loop |
| TEST 011 | Invalid file | random bytes and renamed executable rejected, no AI run | input validation |
| TEST 012 | Oversized file | `FILE_TOO_LARGE`, no AI run | input validation |
| TEST 013 | Mixed formats | same case as PDF / DOCX / PNG → identical fields | consistency |
| TEST 014 | Regression suite | 6 golden documents unchanged | regressions (BUG-01, BUG-02) |

## Bug replay: proving the tests are useful

A test that never fails proves little. `tests/e2e/test_scenarios.py::test_each_synthetic_bug_is_detected`
switches each synthetic bug on and asserts that its scenario fails:

| Replay switch | Scenarios that must fail |
|---|---|
| `docx_routing` | TEST 002, 013, 014 (006 fails too: its fixture is a DOCX) |
| `category_substring` | TEST 014 |
| `duplicate_no_idempotency` | TEST 009 |
| `fallback_mislabel` | TEST 007 |
| `missing_as_zero` | TEST 005 |

## Test history (database)

`scripts/build_dataset.py` really executes the suite eight times with the switches active until each
fix: 7/14 → 10/14 → 11/14 → 12/14 → **8/14 (regression caught)** → 13/14 → 14/14 → 14/14. It is stored in
`test_runs` / `test_results`, shown on the **AI Tests** page, in SQL Q16-Q18 and on Power BI page 4. The
*Run test suite now* button adds a live run.

## Manual checks (UI)

1. New Case → each sample: status, flags and confidence match expectations.
2. Degraded photo: missing fields highlighted in red; correct them; confirm; the case shows *corrected* per field.
3. Confirm twice quickly → one case. Re-upload the same sample → "Duplicate prevented" with a link.
4. *Simulate a primary provider outage* → draft produced, badge "fallback: PROVIDER_TIMEOUT".
5. *Simulate both providers down* → structured error, nothing saved as a case.
6. Case page → Generate Case Summary (notice shown); assistant chips (notice shown; legal advice refused).
7. Audit page: events present, no document text.

## What is not tested (and why)

- Real OCR on real scans: no OCR engine is bundled (see Limitations).
- Live external providers: they need a key; the tests prove they are skipped safely without one.
- Browser automation of the UI: covered by the HTTP e2e tests plus the manual checklist.
