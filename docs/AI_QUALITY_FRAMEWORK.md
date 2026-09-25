# AI quality framework

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Quality is measured on the **whole workflow**, not only on the model's answer: did the document go
through, are the fields right, is anything missing, did the human have to fix it, did the system fail
safely, do the tests still pass?

## Ground truth

Every generated document has its expected values in `data/ground_truth.json` (310 documents + 9
samples). `ai/evaluation.py` compares the canonical forms:

- text fields: whitespace collapsed, trailing dot removed, case-insensitive;
- dates: set of `(label, ISO date, incomplete)`; amounts: set of `(label, value rounded to 0.01)`;
- `null == null` is **correct**. When the document does not contain a field, the right answer is "missing";
- no ground truth → `is_correct = NULL` (unknown), never counted as wrong. This applies to live uploads.

For degraded documents the ground truth is what is **printed on the paper**, not what the noisy text
layer says. For contradictory documents it is the value the document says prevails ("revised,
supersedes the amount above").

## Metrics (one definition, used everywhere)

The same definition is used in the SQL views (`sql/views.sql`), the DAX measures
(`powerbi/DAX_MEASURES.md`), the app and the tests.

| Metric | Definition | Value (dataset) |
|---|---|---:|
| **Document success rate** (AI success rate, extraction) | extraction runs without error / extraction runs | **91.7%** (320 / 349) |
| **Field accuracy** | correct fields / fields with ground truth | **92.9%** |
| **Completeness** | fields found / fields present in the document | **97.9%** |
| **Manual correction rate** | fields changed by the reviewer / fields reviewed | **6.4%** (150 fields) |
| **Confidence score** | mean overall confidence of successful extractions (demonstration metric) | **0.89** |
| **Fallback rate** | extraction runs where the primary failed and the fallback was invoked / extraction runs | **9.7%** (34) |
| **Error rate** | extraction runs ended in error / extraction runs | **8.3%** (29) |
| **Test pass rate** | tests passed / tests executed (latest run; all runs) | **100%** (14/14); 79.5% over 8 runs (89 / 112) |
| **Latency** | mean processing time of extraction runs (latency model in the dataset) | **1.68 s** |
| **Human review rate** | successful extractions flagged *Needs Review* or *Missing Information* / successful extractions | **27.8%** (89 / 320) |
| Regression failures | scenarios that passed in the previous run and fail now | 4 (run #5) |
| Create Case success rate | successful primary extractions that became a case | 95.6% (the other 12 were blocked duplicates) |

AI runs of every task (extraction, category suggestion, summary, assistant): 892 runs, 96.7% success.

## Confidence

Each field gets a confidence from **how** it was found, scaled by the text quality of the document:

| Method | Confidence | Meaning |
|---|---:|---|
| `label` | 0.95 | exact labelled line (`Client: ...`) |
| `heading` | 0.93 | document type found in the heading |
| `ocr_tolerant_label` | 0.72 | label found only with OCR-confusion tolerance (`Cl1ent;`) |
| `gazetteer` | 0.68 | court name found in the narrative, not labelled |
| conflict | × 0.6 | two different values for the same field |
| incomplete date | 0.50 | month and year only |
| missing | 0.00 | not found |

Overall confidence = mean of the 9 field confidences. Below **0.80**, or with a conflict or an
incomplete date, the draft is *Needs Review*. With a required field missing, it is *Missing
Information*.

These numbers are demonstration metrics, not calibrated probabilities. They are still useful, and SQL
Q06 checks that on the data:

| Confidence band | Runs | Field accuracy | Manual correction |
|---|---:|---:|---:|
| ≥ 0.90 | 212 | 98.4% | 1.7% |
| 0.80-0.89 | 67 | 89.9% | 8.7% |
| 0.70-0.79 | 31 | 74.2% | 21.8% |
| < 0.70 | 10 | 54.4% | 46.0% |

## Status rules

| Status | Rule | Share of drafts |
|---|---|---:|
| Complete | all required fields, no conflict, no incomplete date, confidence ≥ 0.80 | 72.2% |
| Needs Review | conflict, incomplete date or confidence < 0.80 | 8.4% |
| Missing Information | a required field (reference, client, opposing party, jurisdiction, dates, claimed amount, category) is missing | 19.4% |

Every draft, including *Complete* ones, is validated by a human before it becomes a case.

## Where to look

- App: **AI Quality** page (live from the views); **Dashboard** for the headline.
- SQL: `sql/analysis_queries.sql` → `docs/SQL_ANALYSIS_RESULTS.md` (26 queries).
- Power BI: `powerbi/` (5 pages, 42 measures).
