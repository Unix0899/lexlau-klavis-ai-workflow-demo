"""End-to-end extraction of one document:

    upload -> ingestion (format, text) -> AI extraction (with fallback)
           -> category suggestion (with fallback) -> checks (missing, incomplete, conflicts)
           -> structured JSON draft for human review

The output is a *draft*: nothing becomes a case until a human validates it.
"""
import hashlib
import time

from .config import AI_DRAFT_NOTICE, REQUIRED_FIELDS, REVIEW_CONFIDENCE_THRESHOLD, SCORED_FIELDS
from .fallback import run_with_fallback
from .ingestion import IngestionError, detect_format, ingest, text_quality
from .registry import build_chain

STATUS_COMPLETE, STATUS_REVIEW, STATUS_MISSING = "Complete", "Needs Review", "Missing Information"
UPLOAD_REJECTIONS = {"EMPTY_FILE", "FILE_TOO_LARGE", "UNSUPPORTED_FORMAT"}


def extract_document(content: bytes, filename: str, providers=None, simulate=None):
    started = time.perf_counter()
    providers = providers or build_chain()
    simulate = simulate or {}

    try:
        doc = ingest(content, filename)
    except IngestionError as exc:
        base = {"error_code": exc.code, "message": exc.message, "processing_ms": _ms(started),
                "attempts": [], "provider_used": None, "fallback_used": False,
                "fallback_reason": None}
        if exc.code in UPLOAD_REJECTIONS:
            # the upload itself is refused: no AI run is started
            return {**base, "status": "rejected"}
        # accepted file whose text could not be extracted: a failed run at the text stage
        return {**base, "status": "error", "error_stage": "text_extraction",
                "ingestion": {"format": detect_format(content), "pages": None,
                              "byte_size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                              "warnings": [], "text_quality": None}}

    ingestion = {"format": doc.format, "pages": doc.pages, "byte_size": doc.byte_size,
                 "sha256": doc.sha256, "warnings": doc.warnings,
                 "text_quality": text_quality(doc.text)}

    run = run_with_fallback("extract", providers, doc.text, simulate=simulate.get("extract"))
    if run["status"] == "error":
        return {**run, "status": "error", "error_stage": "ai_provider", "ingestion": ingestion,
                "text": doc.text, "processing_ms": _ms(started)}

    cat_run = run_with_fallback("suggest_category", providers, doc.text,
                                simulate=simulate.get("suggest_category"))
    result = build_result(run["output"], cat_run)
    summary_provider = next(p for p in providers if p.name == run["attempts"][-1]["provider"])
    result["summary"] = summary_provider.summarise(result)
    return {"status": "success", "ingestion": ingestion, "text": doc.text,
            "provider_used": run["provider_used"], "fallback_used": run["fallback_used"],
            "fallback_reason": run["fallback_reason"], "attempts": run["attempts"],
            "category_run": {k: cat_run[k] for k in ("status", "provider_used", "fallback_used",
                                                     "fallback_reason", "attempts")},
            "result": result, "notice": AI_DRAFT_NOTICE, "processing_ms": _ms(started)}


def build_result(output, cat_run):
    fields = output["fields"]
    result = {name: fields[name]["value"] for name in fields if name in SCORED_FIELDS}
    confidence = {name: fields[name]["confidence"] for name in fields if name in SCORED_FIELDS}
    methods = {name: fields[name].get("method") for name in fields if name in SCORED_FIELDS}
    if cat_run["status"] == "success":
        cat = cat_run["output"]
        result["case_category"] = cat["category"]
        confidence["case_category"] = round(cat["confidence"], 3)
        methods["case_category"] = "keyword_taxonomy"
        result["category_scores"] = cat.get("scores", {})
    else:
        result["case_category"] = None
        confidence["case_category"] = 0.0
        methods["case_category"] = None
    conflicts = output.get("conflicts", [])
    missing, issues = check_fields(result, conflicts)
    score = round(sum(confidence.get(f, 0.0) for f in SCORED_FIELDS) / len(SCORED_FIELDS), 3)

    if missing:
        status = STATUS_MISSING
    elif conflicts or any(i.startswith("date incomplete") for i in issues) \
            or score < REVIEW_CONFIDENCE_THRESHOLD:
        status = STATUS_REVIEW
    else:
        status = STATUS_COMPLETE
    result.update({"missing_fields": missing, "issues": issues, "conflicts": conflicts,
                   "field_confidence": confidence, "field_method": methods,
                   "confidence_score": score, "case_status": status})
    return result


def check_fields(result, conflicts):
    missing, issues = [], []
    for name in REQUIRED_FIELDS:
        value = result.get(name)
        if name == "amounts":
            present = any(a.get("label") == "amount_claimed" and a.get("value") is not None
                          for a in value or [])
        elif name == "important_dates":
            present = any(d.get("date") or d.get("incomplete") for d in value or [])
        else:
            present = bool(value)
        if not present:
            missing.append(name)
            issues.append(f"{name.replace('_', ' ')} missing")
    for d in result.get("important_dates") or []:
        if d.get("incomplete"):
            issues.append(f"date incomplete: {d['label'].replace('_', ' ')} ({d.get('raw')})")
        elif not d.get("date"):
            issues.append(f"date unreadable: {d['label'].replace('_', ' ')}")
    for c in conflicts:
        issues.append(f"conflicting values: {c.get('label') or c['field']}".replace("_", " "))
    return missing, issues


def _ms(started):
    return round((time.perf_counter() - started) * 1000, 1)
