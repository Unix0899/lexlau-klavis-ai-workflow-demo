"""Generate Case Summary: structured case fields -> short draft summary.

Only the structured fields are sent to the provider (data minimisation), never the
full document. The summary is always returned with the mandatory notice.
"""
from .config import AI_DRAFT_NOTICE
from .fallback import run_with_fallback
from .registry import build_chain

SUMMARY_FIELDS = ("case_title", "case_reference", "client_name", "opposing_party", "jurisdiction",
                  "important_dates", "amounts", "case_category", "missing_fields")


def generate_case_summary(case: dict, providers=None, simulate=None):
    minimal = {k: case.get(k) for k in SUMMARY_FIELDS}
    run = run_with_fallback("summarise", providers or build_chain(), minimal, simulate=simulate)
    if run["status"] == "success":
        run["summary"] = run.pop("output")
    run["notice"] = AI_DRAFT_NOTICE
    return run
