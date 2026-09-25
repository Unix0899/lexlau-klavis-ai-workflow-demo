"""Controlled logging: metadata only, never document content.

Logged:     document_id, format, processing_status, latency, provider, error_code ...
Never:      full document content, extracted text, client secrets, unnecessary PII.

Two safety nets:
1. an allow-list of keys: anything else is dropped (and counted);
2. a redactor for free-text values (e-mail, phone, IBAN, national-number patterns),
   plus a length cap so a long text can never slip through.
"""
import json
import re
import threading
from datetime import datetime, timezone

from .config import LOG_PATH

ALLOWED_KEYS = {
    "event_type", "actor", "entity_type", "entity_id", "document_id", "ai_run_id", "case_id",
    "test_run_id", "format", "processing_status", "latency_ms", "provider", "fallback_used",
    "fallback_reason", "error_code", "byte_size", "pages", "confidence_score", "case_status",
    "fields_corrected", "fields_reviewed", "field_name", "task", "duplicate_of", "tests_passed",
    "tests_failed", "bug_replay", "warning_count", "missing_count", "conflict_count", "http_status",
    "path", "method",
}
MAX_VALUE_CHARS = 80

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}\b"), "[REDACTED_IBAN]"),
    (re.compile(r"\b\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}\b"), "[REDACTED_NATIONAL_NUMBER]"),
    (re.compile(r"(?<!\w)\+?\d[\d ./-]{7,}\d(?!\w)"), "[REDACTED_PHONE]"),
]
_lock = threading.Lock()


def redact_text(value: str) -> str:
    for rx, repl in _PATTERNS:
        value = rx.sub(repl, value)
    return value


def sanitize(fields: dict) -> dict:
    clean, dropped = {}, 0
    for key, value in fields.items():
        if key not in ALLOWED_KEYS:
            dropped += 1
            continue
        if isinstance(value, str):
            value = redact_text(value)
            if len(value) > MAX_VALUE_CHARS:
                value = value[:MAX_VALUE_CHARS] + "...[truncated]"
        elif isinstance(value, (list, dict)):
            value = f"[{type(value).__name__} omitted]"
        clean[key] = value
    if dropped:
        clean["dropped_keys"] = dropped
    return clean


def log_event(event_type: str, log_path=None, **fields) -> dict:
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              **sanitize({"event_type": event_type, **fields})}
    target = log_path or LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
