# Working under technical supervision: review workflow

> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

## In the real professional context

At LexLau (Klavis.app / KlavIA), Harry worked as an **AI Engineer & Data Analyst intern under the
supervision of the CTO / technical supervisor**:

- changes were made under technical supervision, on branches, through Merge Requests;
- problems were documented (what was observed, how to reproduce it, what was expected);
- corrections were **reviewed by the supervisor**. Harry did not approve his own changes;
- tests could be replayed, and results (including failures) were reported to the supervisor;
- a change was not considered finished just because it worked locally.

Harry was not the CTO, the lead architect, the owner of the architecture, or the sole developer. He
contributed to the development, testing and improvement of AI-enabled workflows under technical
supervision.

## How the public reconstruction simulates this

There is only one author in this repository, so the review is **simulated as a written procedure and
checklists**. That makes the method visible without pretending a reviewer approved anything here.

```text
Issue ─► Reproduction ─► Analysis ─► Implementation ─► Automated tests ─► Manual tests ─► Review ─► Retest ─► Closure
```

| Step | What is produced | Where, in this repository |
|---|---|---|
| Issue | Symptom in one sentence, impact, first occurrence | "Symptom" rows of `BUG_INVESTIGATION_CASES.md` |
| Reproduction | Minimal steps + replay switch + failing scenario | `ai/bug_replay.py`, `LEXLAU_BUG_REPLAY=...` |
| Analysis | Hypothesis, then evidence (logs, scores, SQL) | "Hypothesis / Root cause" rows; SQL Q03, Q23 |
| Implementation | Fix on a feature branch (`fix/docx-content-routing` ...) | test run labels in `test_runs` |
| Automated tests | Unit test for the root cause + scenario suite | `tests/unit`, `tests/e2e/scenarios.py` |
| Manual tests | UI walkthrough of the affected flow | checklist below |
| Review | Reviewer checklist, done by someone other than the author | checklist below |
| Retest | Full regression suite on the merged code | runs #2, #3, #4, #6, #7, #8 |
| Closure | Final status + product feedback | "Final status" rows |

## Feature-branch test report (template)

```text
Branch:            fix/<short-name>
Issue:             BUG-0x - <one line>
Root cause:        <one sentence>
Change:            <files, behaviour before / after>
Automated tests:   python scripts/run_tests.py  ->  <n> passed, <n> failed
Scenario suite:    TEST 001-014  ->  <n>/14 (attach the failing ones before the fix)
Manual test:       <flow, sample document, result>
Data impact:       <SQL query + before/after numbers>
Risks / follow-up: <what is not covered>
```

## QA checklist (author, before asking for review)

- [ ] The bug is reproduced by a test that **fails before** the fix
- [ ] The same test **passes after** the fix; the full suite is green (`python scripts/run_tests.py`)
- [ ] PDF, DOCX and image paths still behave the same (TEST 013)
- [ ] Error paths return a structured error (no crash, no traceback, nothing saved by mistake)
- [ ] No document content, personal data or secret added to logs (`tests/unit/test_safe_logging.py`)
- [ ] Metrics still mean what their definition says (fallback, missing, accuracy)
- [ ] Documentation updated (bug case, data dictionary if the schema changed)

## Review checklist (reviewer)

- [ ] The root cause is explained, not only the symptom
- [ ] The fix is the smallest change that removes the cause
- [ ] Tests would have caught the bug, and would catch its return
- [ ] No behaviour change for unaffected formats / providers
- [ ] Data protection rules respected (minimisation, redaction, no secrets)
- [ ] Decision: approve / request changes. **The author does not approve their own change**

## Final validation (before closure)

- [ ] Regression suite green on the merged version (latest run #8: 14/14)
- [ ] Before/after evidence recorded (test runs, SQL numbers)
- [ ] Product feedback written when the bug reveals a UX or process issue

The regression in run #5 is why the last step exists: a merge re-introduced BUG-01 and the suite caught
it before release.
