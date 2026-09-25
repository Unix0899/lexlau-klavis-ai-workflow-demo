# Recruiter guide (10 minutes)

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

## In one paragraph

At LexLau, Harry Mulembwe worked as an **AI Engineer & Data Analyst intern** on Klavis.app / KlavIA, a
legal case-management application with many AI features, **under the supervision of the CTO**. He
contributed to the development, testing and improvement of AI-enabled workflows: he tested AI features
systematically, structured and analysed data, reproduced bugs, documented expected vs actual behaviour
and turned test results into product and technical feedback. The real work is confidential. This
repository is a **public reconstruction** of the same kind of workflow, written from scratch with
synthetic data.

## What to look at, in order

| Minutes | Look at | You will see |
|---|---|---|
| 1 | `proofs/proof_01_ai_extraction.png` | a synthetic document turned into structured, scored fields |
| 1 | `proofs/proof_02_human_validation.png` | the AI flags missing fields; a human corrects; the case records what changed |
| 2 | `proofs/proof_04_test_suite.png` | TEST 001-014 across 8 runs: bugs, fixes, a caught regression |
| 2 | `docs/BUG_INVESTIGATION_CASES.md` + `proof_05` | symptom → reproduction → root cause → fix → retest |
| 1 | `proofs/proof_07_sql_analysis.png`, `sql/analysis_queries.sql` | real SQL with window functions, answering real questions |
| 1 | `proofs/proof_06_ai_quality_dashboard.png`, `powerbi/screenshots/` | Power BI report (5 pages); star schema; 42 DAX measures reconciled with SQL (85/85) |
| 1 | `docs/DATA_PRIVACY.md`, `proof_08` | data minimisation, redacted logging, audit |
| 1 | `docs/CTO_REVIEW_WORKFLOW.md` | how work under technical supervision was organised |

Run it: `pip install -r requirements.txt` then `python -m app.backend.server` →
http://127.0.0.1:8765 (no API key).

## Real experience vs public reconstruction

| Real professional experience (LexLau) | Public portfolio reconstruction (this repo) |
|---|---|
| AI-enabled application testing | Synthetic legal documents (PDF, DOCX, images; 8 variants) |
| Data analysis and structuring | Synthetic SQLite database (9 tables, 6 views) |
| AI workflow validation | Public AI workflow with provider fallback and human validation |
| Bug reproduction | Automated tests (73) incl. TEST 001-014 and bug replay |
| Documentation | SQL analytics (26 queries) |
| Product / technical feedback | AI quality dashboard (app + Power BI model) |
| Confidential-data awareness | Technical documentation |
| Work under CTO / technical supervision | Reproducible demo (one command) |

The public project is a reconstruction designed to demonstrate the workflow without exposing
LexLau/Klavis intellectual property or confidential client information.

## What this project does NOT claim

- It is not Klavis, and not a copy of its code, prompts, schemas or architecture.
- Harry did not build Klavis. He was not the CTO, the lead architect or the sole developer, and he did
  not approve his own changes.
- The bugs are synthetic. They illustrate the *type* of issues investigated.
- The metrics describe the synthetic dataset, not the production system.

## Questions Harry can answer in an interview

1. Why is "missing" stored as `null` and counted as correct when the document has no value? (BUG-05, evaluation rules)
2. How do you know your tests would catch a bug? (bug replay: every switch makes its scenario fail)
3. Why did the fallback rate read 0% before BUG-04 was fixed, and why does that matter for monitoring?
4. How would you calibrate confidence on real data? What does Q06 show?
5. Why two duplicate guards (idempotency key + unique reference)?
6. What would change before sending real documents to an external LLM? (DPA, legal basis, minimisation)
7. Why do most failures here come from document routing and not from the model?
8. How is a change reviewed before it is considered finished? (CTO review workflow)
9. What are the limits of the synthetic data and of the mock AI?
10. How do the SQL views, the DAX measures and the app stay consistent? (one definition per metric; reconciliation script)
