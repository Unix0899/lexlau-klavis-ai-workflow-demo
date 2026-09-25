"""Compare extracted values with the ground truth (data/ground_truth.json).

A field is correct when its canonical form equals the canonical ground-truth value.
Absent in the document and absent in the output (null == null) counts as correct:
the system correctly reported the field as missing.
"""
import json
import re

LIST_FIELDS = ("important_dates", "amounts")


def _norm_text(v):
    if v is None:
        return None
    v = re.sub(r"\s+", " ", str(v)).strip().rstrip(".").casefold()
    return v or None


def canonical(field, value):
    """Stable, comparable representation (also what is stored in extracted_fields)."""
    if field == "important_dates":
        items = sorted((d.get("label"), d.get("date"), bool(d.get("incomplete")))
                       for d in value or [])
        return json.dumps(items) if items else None
    if field == "amounts":
        items = sorted((a.get("label"), None if a.get("value") is None else round(float(a["value"]), 2))
                       for a in value or [])
        return json.dumps(items) if items else None
    return _norm_text(value)


def is_correct(field, ai_value, expected):
    return canonical(field, ai_value) == canonical(field, expected)


def to_storage(field, value):
    """JSON text for list fields, plain text otherwise (None stays NULL)."""
    if field in LIST_FIELDS:
        return json.dumps(value, ensure_ascii=False) if value else None
    return value if value not in ("", None) else None


def from_storage(field, value):
    if value is None:
        return [] if field in LIST_FIELDS else None
    if field in LIST_FIELDS:
        return json.loads(value)
    return value
