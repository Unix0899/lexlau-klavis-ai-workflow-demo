"""Bug replay switches (all OFF by default).

The five synthetic bugs documented in docs/BUG_INVESTIGATION_CASES.md are kept in
the code behind these switches so that anyone can reproduce the faulty behaviour,
watch the regression tests fail, then switch the bug off and watch them pass.

These scenarios reproduce the type of AI workflow issues investigated during the
professional experience, using fully synthetic implementations. They are not the
production bugs of Klavis.

    LEXLAU_BUG_REPLAY=docx_routing,missing_as_zero python -m app.backend.server

or, in code / tests:

    with bug_replay("category_substring"):
        ...
"""
import os
import threading
from contextlib import contextmanager

BUGS = {
    "docx_routing": "BUG-01 DOCX routed to the PDF parser (routing by extension table)",
    "category_substring": "BUG-02 Category keywords matched inside other words ('board' in 'cardboard')",
    "duplicate_no_idempotency": "BUG-03 Double submission creates two cases (no idempotency / duplicate check)",
    "fallback_mislabel": "BUG-04 Fallback result recorded under the primary provider name",
    "missing_as_zero": "BUG-05 Missing amount returned as 0.00 instead of null (not reported missing)",
}

_local = threading.local()


def _env_flags():
    raw = os.environ.get("LEXLAU_BUG_REPLAY", "")
    return {f.strip() for f in raw.split(",") if f.strip()}


def active():
    return _env_flags() | getattr(_local, "flags", set())


def is_on(name):
    if name not in BUGS:
        raise KeyError(f"Unknown bug replay flag: {name}")
    return name in active()


@contextmanager
def bug_replay(*names):
    for n in names:
        if n not in BUGS:
            raise KeyError(f"Unknown bug replay flag: {n}")
    previous = getattr(_local, "flags", set())
    _local.flags = set(previous) | set(names)
    try:
        yield
    finally:
        _local.flags = previous
