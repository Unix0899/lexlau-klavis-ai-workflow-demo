# Insights and product feedback

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
> Every number below is **from the synthetic demonstration dataset** (`database/klavis_ai_demo.sqlite`);
> it says nothing about the performance of Klavis. The value is in the method: measure, explain, recommend.

## 1. Most failed runs came from document handling, not from the AI

25 of the 29 failed extraction runs are DOCX `PARSE_ERROR`s from the routing bug (BUG-01). The other 4 are
provider outages where both providers failed. After the fix: 0 DOCX parse errors in 104 runs (SQL Q03,
Q08).
**Feedback:** monitor failures **by stage** (text extraction vs AI provider). A "model quality" problem
is often a pipeline problem.

## 2. Scan quality drives field quality

| Variant | Field accuracy | Manual correction | Review rate |
|---|---:|---:|---:|
| clean (PDF / DOCX / images) | 99.7% | ≈ 0.4% | ≈ 1% |
| multipage PDF | 99.4% | 0.7% | 5.6% |
| degraded (poor scans, photos) | 65.5% | 29.5-42.9% | 63-100% |

**Feedback:** ask for a better scan early (upload-time quality warning from `text_quality`), and route
degraded documents straight to a careful review instead of presenting them like clean ones.

## 3. Confidence is a usable routing signal

Runs with confidence ≥ 0.90 have 98.4% field accuracy; below 0.70 only 54.4% (SQL Q06). The 0.80
review threshold sends the right drafts to closer review.
**Feedback:** show the confidence per field (done in the UI) and sort the review queue by confidence.
Before using the scores as probabilities, calibrate them on real, consented data.

## 4. The fallback keeps the service up, at a lower quality

The fallback rescued 30 of 34 runs whose primary failed (Q09). Its drafts are less accurate (89.6% vs
93.2% field accuracy, Q11) and less confident (0.80 vs 0.90).
**Feedback:** label fallback drafts in the UI (done: "fallback" badge) and track the fallback rate as an
operations KPI. It was invisible while BUG-04 recorded the wrong provider.

## 5. The hardest fields are dates, jurisdiction and title

Accuracy: dates 87.8%, jurisdiction 89.1%, case title 89.7%, against 96-98% for reference, document
type and category (Q04). Long free-text values are the most exposed to OCR noise, and jurisdiction is
where contradictions happen.
**Feedback:** give these fields the most visible place in the review form, and validate dates against
simple rules (a deadline after the notice date).

## 6. Contradictions are detected but not resolved

All contradictory documents were flagged *Needs Review*, yet the extraction kept the first value, so
field accuracy is 88.9% on that variant.
**Feedback:** when a later statement says it *supersedes* an earlier one, propose that value, and
always show both values side by side to the reviewer.

## 7. "Missing" is information

Documents with missing fields are handled correctly: 99.6% accuracy, because absent = `null` is the
right answer, and 100% are routed to review (Q15 separates "correctly reported missing" from "missed
by the extraction").
**Feedback:** turn missing fields into a follow-up task ("request the claimed amount from the client").
The case status *Awaiting information* is a first step.

## 8. Guards matter as much as models

12 duplicate cases were blocked and 3 repeated submissions ignored, with 0 duplicate references among
260 cases (Q20-Q21). 8 invalid or oversized uploads were rejected before any AI call.

## 9. Tests turned fixes into lasting fixes

The suite went 7/14 → 14/14 across 8 runs. It caught a regression (run #5) that re-introduced BUG-01
through a merge.
**Feedback:** run TEST 001-014 on every merge request, not only on the fixing branch.

## Summary of recommendations

| # | Recommendation | Metric to follow |
|---|---|---|
| 1 | Separate text-extraction failures from AI failures in monitoring | error rate by stage |
| 2 | Warn about poor scans at upload | accuracy on degraded documents |
| 3 | Sort the review queue by confidence | correction rate by band |
| 4 | Show fallback drafts as such; alert on the fallback rate | fallback rate |
| 5 | Show conflicting values side by side; prefer the "supersedes" value | accuracy on contradictory documents |
| 6 | Turn missing fields into follow-up tasks | time to complete a case |
| 7 | Scenario suite on every merge | regression failures |
