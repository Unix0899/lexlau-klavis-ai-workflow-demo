# Bug investigation cases

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

These scenarios reproduce the type of AI workflow issues investigated during the professional
experience, using fully synthetic implementations. **They are not the production bugs of Klavis**, and
the code they live in is not Klavis code.

Each bug is kept in the code behind a replay switch (`ai/bug_replay.py`, OFF by default), so you can
reproduce it, watch its regression test fail, switch it off and watch the test pass:

```bash
LEXLAU_BUG_REPLAY=docx_routing python -m app.backend.server      # replay in the app
python -m unittest tests.e2e.test_scenarios                        # the suite proves each bug is caught
```

The test history in the database (`test_runs`, 8 runs) is the result of **really executing** the suite
with the switches on until each (synthetic) fix date. Dates are part of the synthetic timeline.

| ID | Bug | Caught by | Failing runs | Fixed in |
|---|---|---|---|---|
| BUG-01 | DOCX routed to the PDF parser | TEST 002, 006, 013, 014 | #1, then #5 (regression) | #2, again #6 |
| BUG-02 | Category keyword matched inside another word | TEST 014 | #1-#2 | #3 |
| BUG-03 | Double submission creates duplicate cases | TEST 009 | #1-#6 | #7 |
| BUG-04 | Fallback result recorded under the primary provider | TEST 007 | #1-#5 | #6 |
| BUG-05 | Missing amount returned as 0.00 | TEST 005 | #1-#3 | #4 |

---

## BUG-01 · DOCX not routed correctly

| Step | |
|---|---|
| **Symptom** | Every DOCX upload fails at the text stage. PDF and images work. Users re-upload as PDF. |
| **Reproduction** | `LEXLAU_BUG_REPLAY=docx_routing`; upload `02_employment_letter.docx`: `PARSE_ERROR` 3/3 times. Same file content renamed `.pdf`: works. |
| **Observed result** | `status=error error=PARSE_ERROR stage=text_extraction` (TEST 002), no fields, no case. |
| **Expected result** | DOCX text extracted; the same case in PDF / DOCX / PNG gives identical fields (TEST 013). |
| **Hypothesis** | The error message comes from the PDF library, not from the DOCX reader, so the file reaches the wrong parser. |
| **Root cause** | Routing used a table keyed on the file extension. It contained `.doc` but not `.docx`, and unknown extensions defaulted to the PDF parser. |
| **Fix** | Route on the **content**: magic bytes, plus `word/document.xml` present in the ZIP. The extension only produces a warning when it disagrees. |
| **Retest** | `test_bug01_replay_routes_docx_to_pdf_parser`, TEST 002 / 006 / 013 / 014 green. Dataset: DOCX `PARSE_ERROR` **25/25 before** the fix, **0/104 after** (SQL Q03). 24 of the 25 failed intakes were recovered by a re-submission (`vw_error_analysis`). |
| **Final status** | Closed after review (run #2). A later merge re-introduced the old routing (run #5): **TEST 002, 006, 013 and 014 flagged it as a regression** before release. It was reverted in run #6. |

## BUG-02 · Category mismatch

| Step | |
|---|---|
| **Symptom** | Some invoice disputes about packaging are suggested as *Corporate matter*. |
| **Reproduction** | `LEXLAU_BUG_REPLAY=category_substring`; `09_cardboard_invoice_dispute.pdf` → Corporate matter. |
| **Observed result** | TEST 014: `cardboard_commercial.pdf:case_category` differs from the golden output. |
| **Expected result** | Commercial dispute (unpaid invoices, goods supplied). |
| **Hypothesis** | A Corporate keyword is found where it should not be. The keyword scores show "board" counted once per "cardboard". |
| **Root cause** | Keywords were counted as plain substrings: `board` matched inside `cardboard`. |
| **Fix** | Word-boundary matching (`(?<![a-z])keyword(?![a-z])`). Phrases keep a double weight. The suggestion stays editable by the reviewer. |
| **Retest** | Unit test `test_word_boundary_and_bug02_replay`; TEST 014 green from run #3. Dataset: **4 category corrections before** the fix (all on "cardboard" documents), **0 after** (SQL Q23). |
| **Final status** | Closed. Product feedback: show the category as a suggestion with its confidence, never as a decision. |

## BUG-03 · Duplicate case creation

| Step | |
|---|---|
| **Symptom** | Two or three identical cases appear after one validation. |
| **Reproduction** | `LEXLAU_BUG_REPLAY=duplicate_no_idempotency`; click *Confirm & create case* twice, then upload the same document again and confirm. |
| **Observed result** | TEST 009: `cases created=3; submissions -> created, created, created`. |
| **Expected result** | One case. The repeated click returns the existing case; the re-upload is blocked with a link to the existing case. |
| **Hypothesis** | Nothing identifies a submission, and nothing identifies a case as already existing. |
| **Root cause** | The create path had no idempotency key and did not fill the normalised `reference_key`, so the UNIQUE constraint never applied. |
| **Fix** | Two guards: an idempotency key per submission (repeat → `existing`) and a normalised reference checked before insert and enforced by `UNIQUE(reference_key)` → `409 DUPLICATE_CASE`. The button is also disabled while the request runs. |
| **Retest** | TEST 009 green from run #7; HTTP e2e test (`201` then `200 existing`, then `409`). Dataset: **12 duplicate cases blocked**, **3 repeated submissions ignored**, **0 duplicate references** among 260 cases (SQL Q20-Q21). |
| **Final status** | Closed. |

## BUG-04 · Provider fallback problem

| Step | |
|---|---|
| **Symptom** | The fallback rate on the dashboard stays at 0% while provider timeouts are known to happen. |
| **Reproduction** | `LEXLAU_BUG_REPLAY=fallback_mislabel`; New Case → *Simulate a primary provider outage*. |
| **Observed result** | TEST 007: `stored provider_used=mock-primary, fallback_used=0, reason=PROVIDER_TIMEOUT`. The run is saved as a primary success. |
| **Expected result** | `provider_used=mock-fallback, fallback_used=1, reason=PROVIDER_TIMEOUT`. |
| **Hypothesis** | The fallback works (the answer is there) but its bookkeeping is wrong. The data contradicts itself: a fallback reason on a run without fallback. |
| **Root cause** | The chain returned the name of the first provider of the chain instead of the provider whose answer was kept. |
| **Fix** | Record `provider_used` from the successful attempt and keep every attempt (`provider`, `status`, `error_code`, `latency_ms`). |
| **Retest** | Unit test `test_bug04_replay_mislabels_provider`; TEST 007 green from run #6. Dataset: fallback rate **9.7%** (34 of 349 extractions), which the bug would have reported as 0%. |
| **Final status** | Closed. Lesson: a monitoring metric is only as good as the code that records it. |

## BUG-05 · Missing-field bug

| Step | |
|---|---|
| **Symptom** | Some cases show a claimed amount of EUR 0.00 and are marked Complete. |
| **Reproduction** | `LEXLAU_BUG_REPLAY=missing_as_zero`; `05_missing_fields_notice.pdf` (no amount in the document). |
| **Observed result** | TEST 005: `missing_fields=['jurisdiction']; amounts=[0.0]`. The amount is not reported missing. |
| **Expected result** | `amounts` in `missing_fields`, value `null`, status *Missing Information*. |
| **Hypothesis** | A default value is used when the label is absent. |
| **Root cause** | The extractor inserted a 0.00 default when no amount line was found, so the completeness check saw a value. |
| **Fix** | Absent means `null`. The check requires an `amount_claimed` with a non-null value. Rule written down: *missing ≠ zero*. |
| **Retest** | Unit test `test_missing_amount_is_null_not_zero`; TEST 005 green from run #4. |
| **Final status** | Closed. |

---

## How the method maps to the proofs

- `proofs/proof_05_bug_investigation.png`: BUG-01 from symptom to retest.
- `proofs/proof_04_test_suite.png`: the scenario × run matrix (fixes, then the caught regression).
- `docs/CTO_REVIEW_WORKFLOW.md`: how each fix was reviewed before closure.
