"""Resilient provider chain:

    PRIMARY PROVIDER
        | failure (timeout, error, output that breaks the contract)
        v
    FALLBACK PROVIDER
        | failure
        v
    STRUCTURED ERROR  {"status": "error", "error_code": "AI_UNAVAILABLE", ...}

Every attempt is recorded (provider, status, error code, latency) so that the
fallback rate and the error rate can be measured, and the provider that really
produced the answer is always the one stored.
"""
import time

from . import bug_replay
from .provider_interface import ProviderError, validate_category_output, validate_extraction_output

VALIDATORS = {
    "extract": validate_extraction_output,
    "suggest_category": validate_category_output,
    "summarise": lambda out: out if isinstance(out, str) and out.strip() else _bad("Empty summary"),
    "answer": lambda out: out if isinstance(out, str) and out.strip() else _bad("Empty answer"),
}


def _bad(msg):
    from .provider_interface import InvalidProviderOutput
    raise InvalidProviderOutput(msg)


def run_with_fallback(task, providers, *args, simulate=None):
    """Call `task` on each provider in turn until one returns a valid output.

    simulate: optional {provider_name: failure_code} used by tests and the dataset builder.
    """
    simulate = simulate or {}
    attempts = []
    for provider in providers:
        started = time.perf_counter()
        try:
            out = getattr(provider, task)(*args, simulate_failure=simulate.get(provider.name))
            out = VALIDATORS[task](out)
        except ProviderError as exc:
            attempts.append({"provider": provider.name, "status": "failed", "error_code": exc.code,
                             "latency_ms": _ms(started)})
            continue
        attempts.append({"provider": provider.name, "status": "success", "error_code": None,
                         "latency_ms": _ms(started)})
        used = provider.name
        fallback_used = len(attempts) > 1
        if bug_replay.is_on("fallback_mislabel"):
            # BUG-04 replay: the result is stored under the first provider of the chain
            used, fallback_used = providers[0].name, False
        return {"status": "success", "output": out, "provider_used": used,
                "fallback_used": fallback_used,
                "fallback_reason": attempts[0]["error_code"] if len(attempts) > 1 else None,
                "attempts": attempts}
    return {"status": "error", "error_code": "AI_UNAVAILABLE",
            "message": "The AI service is temporarily unavailable. Nothing was saved; "
                       "please retry or enter the case manually.",
            "provider_used": None, "fallback_used": len(attempts) > 1,
            "fallback_reason": attempts[0]["error_code"] if attempts else None,
            "attempts": attempts}


def _ms(started):
    return round((time.perf_counter() - started) * 1000, 1)
