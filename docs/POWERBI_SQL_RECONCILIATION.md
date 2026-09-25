# Power BI ↔ SQL reconciliation

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Run on 25/09/2026 09:54 with `scripts/reconcile_powerbi_sql.py`: the PBIP open in Power BI Desktop, queried **read-only** through Microsoft's Power BI Modeling MCP server, compared with the same numbers computed in SQLite.

**Result: 85/85 comparisons PASS.** (SQL field accuracy by field is rounded to 0.1 % in the view, hence the 0.06-point tolerance on those rows.)

| Scope | Measure | Power BI (DAX) | SQL | Status |
|---|---|---:|---:|---|
| Whole dataset | Total AI Runs | 892.00 | 892.00 | PASS |
| Whole dataset | Successful AI Runs | 863.00 | 863.00 | PASS |
| Whole dataset | Failed AI Runs | 29.00 | 29.00 | PASS |
| Whole dataset | AI Success Rate % | 0.9675 | 0.9675 | PASS |
| Whole dataset | Extraction Runs | 349.00 | 349.00 | PASS |
| Whole dataset | Successful Extractions | 320.00 | 320.00 | PASS |
| Whole dataset | Extraction Success Rate % | 0.9169 | 0.9169 | PASS |
| Whole dataset | Average Confidence | 0.8939 | 0.8939 | PASS |
| Whole dataset | Average Processing Time | 1,680.44 | 1,680.44 | PASS |
| Whole dataset | Fallback Runs | 34.00 | 34.00 | PASS |
| Whole dataset | Fallback Rate % | 0.0974 | 0.0974 | PASS |
| Whole dataset | Error Rate % | 0.0831 | 0.0831 | PASS |
| Whole dataset | Human Review Cases | 89.00 | 89.00 | PASS |
| Whole dataset | Human Review Rate % | 0.2781 | 0.2781 | PASS |
| Whole dataset | PDF Success Rate % | 1.0000 | 1.0000 | PASS |
| Whole dataset | DOCX Success Rate % | 0.7984 | 0.7984 | PASS |
| Whole dataset | Image Success Rate % | 0.9589 | 0.9589 | PASS |
| Whole dataset | Scored Fields | 2,880.00 | 2,880.00 | PASS |
| Whole dataset | Correct Fields | 2,675.00 | 2,675.00 | PASS |
| Whole dataset | Field Accuracy % | 0.9288 | 0.9288 | PASS |
| Whole dataset | Completeness % | 0.9786 | 0.9786 | PASS |
| Whole dataset | Missing Fields | 84.00 | 84.00 | PASS |
| Whole dataset | Missing Rate % | 0.0292 | 0.0292 | PASS |
| Whole dataset | Conflicting Fields | 20.00 | 20.00 | PASS |
| Whole dataset | Avg Field Confidence | 0.9207 | 0.9207 | PASS |
| Whole dataset | Manual Corrections | 150.00 | 150.00 | PASS |
| Whole dataset | Manual Correction Rate % | 0.0641 | 0.0641 | PASS |
| Whole dataset | Tests Executed | 112.00 | 112.00 | PASS |
| Whole dataset | Tests Passed | 89.00 | 89.00 | PASS |
| Whole dataset | Tests Failed | 23.00 | 23.00 | PASS |
| Whole dataset | Test Pass Rate % | 0.7946 | 0.7946 | PASS |
| Whole dataset | Regression Failures | 4.0000 | 4.0000 | PASS |
| Whole dataset | Latest Test Pass Rate % | 1.0000 | 1.0000 | PASS |
| Whole dataset | Test Runs | 8.0000 | 8.0000 | PASS |
| Whole dataset | Reviews | 260.00 | 260.00 | PASS |
| Whole dataset | Reviews With Corrections | 65.00 | 65.00 | PASS |
| Whole dataset | Reviews With Corrections % | 0.2500 | 0.2500 | PASS |
| Whole dataset | Avg Review Time | 70.77 | 70.77 | PASS |
| Whole dataset | Category Changes | 4.0000 | 4.0000 | PASS |
| Whole dataset | Audit Events | 1,603.00 | 1,603.00 | PASS |
| Whole dataset | Files Rejected | 8.0000 | 8.0000 | PASS |
| Whole dataset | Duplicates Blocked | 15.00 | 15.00 | PASS |
| PDF | Extraction Runs | 147.00 | 147.00 | PASS |
| PDF | Extraction Success Rate % | 1.0000 | 1.0000 | PASS |
| PDF | Field Accuracy % | 0.9153 | 0.9153 | PASS |
| DOCX | Extraction Runs | 129.00 | 129.00 | PASS |
| DOCX | Extraction Success Rate % | 0.7984 | 0.7984 | PASS |
| DOCX | Field Accuracy % | 0.9849 | 0.9849 | PASS |
| Image | Extraction Runs | 73.00 | 73.00 | PASS |
| Image | Extraction Success Rate % | 0.9589 | 0.9589 | PASS |
| Image | Field Accuracy % | 0.8746 | 0.8746 | PASS |
| Case title | Field Accuracy % | 0.8969 | 0.8970 | PASS |
| Case title | Missing Fields | 7.0000 | 7.0000 | PASS |
| Case title | Manual Corrections | 24.00 | 24.00 | PASS |
| Case reference | Field Accuracy % | 0.9656 | 0.9660 | PASS |
| Case reference | Missing Fields | 8.0000 | 8.0000 | PASS |
| Case reference | Manual Corrections | 10.00 | 10.00 | PASS |
| Client | Field Accuracy % | 0.9406 | 0.9410 | PASS |
| Client | Missing Fields | 7.0000 | 7.0000 | PASS |
| Client | Manual Corrections | 12.00 | 12.00 | PASS |
| Opposing party | Field Accuracy % | 0.9250 | 0.9250 | PASS |
| Opposing party | Missing Fields | 15.00 | 15.00 | PASS |
| Opposing party | Manual Corrections | 15.00 | 15.00 | PASS |
| Document type | Field Accuracy % | 0.9625 | 0.9630 | PASS |
| Document type | Missing Fields | 12.00 | 12.00 | PASS |
| Document type | Manual Corrections | 9.0000 | 9.0000 | PASS |
| Jurisdiction | Field Accuracy % | 0.8906 | 0.8910 | PASS |
| Jurisdiction | Missing Fields | 21.00 | 21.00 | PASS |
| Jurisdiction | Manual Corrections | 28.00 | 28.00 | PASS |
| Dates | Field Accuracy % | 0.8781 | 0.8780 | PASS |
| Dates | Missing Fields | 0.0000 | 0.0000 | PASS |
| Dates | Manual Corrections | 27.00 | 27.00 | PASS |
| Amounts | Field Accuracy % | 0.9187 | 0.9190 | PASS |
| Amounts | Missing Fields | 14.00 | 14.00 | PASS |
| Amounts | Manual Corrections | 21.00 | 21.00 | PASS |
| Category | Field Accuracy % | 0.9812 | 0.9810 | PASS |
| Category | Missing Fields | 0.0000 | 0.0000 | PASS |
| Category | Manual Corrections | 4.0000 | 4.0000 | PASS |
| 2026-01 | Total AI Runs | 108.00 | 108.00 | PASS |
| 2026-02 | Total AI Runs | 151.00 | 151.00 | PASS |
| 2026-03 | Total AI Runs | 152.00 | 152.00 | PASS |
| 2026-04 | Total AI Runs | 158.00 | 158.00 | PASS |
| 2026-05 | Total AI Runs | 174.00 | 174.00 | PASS |
| 2026-06 | Total AI Runs | 147.00 | 147.00 | PASS |
| 2026-07 | Total AI Runs | 2.0000 | 2.0000 | PASS |
