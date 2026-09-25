"""Demo assistant: questions about the CURRENT synthetic case only.

Demo assistant - not legal advice. Answers are built from the structured,
human-validated case fields; the full document is never sent.
"""
from .config import ASSISTANT_NOTICE
from .fallback import run_with_fallback
from .registry import build_chain
from .summarisation import SUMMARY_FIELDS

MAX_QUESTION_CHARS = 500


def ask(question: str, case: dict, providers=None, simulate=None):
    question = (question or "").strip()[:MAX_QUESTION_CHARS]
    if not question:
        return {"status": "error", "error_code": "EMPTY_QUESTION", "message": "Ask a question.",
                "notice": ASSISTANT_NOTICE}
    minimal = {k: case.get(k) for k in SUMMARY_FIELDS}
    run = run_with_fallback("answer", providers or build_chain(), question, minimal, simulate=simulate)
    if run["status"] == "success":
        run["answer"] = run.pop("output")
    run["notice"] = ASSISTANT_NOTICE
    return run
