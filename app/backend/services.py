"""Application services: persistence of the AI workflow.

    AI proposes  ->  Human reviews  ->  Application persists

Nothing becomes a case without an explicit human validation. Every step writes an
audit event that contains metadata only (never the document text).
"""
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from ai import bug_replay
from ai.assistant import ask
from ai.config import REFERENCE_DATABASE, ROOT, SCORED_FIELDS
from ai.evaluation import canonical, from_storage, is_correct, to_storage
from ai.extraction import check_fields, extract_document
from ai.registry import build_chain
from ai.safe_logging import log_event, sanitize
from ai.summarisation import generate_case_summary

SQL_DIR = ROOT / "sql"
UPLOAD_DIR = ROOT / "app_uploads"


class ServiceError(Exception):
    def __init__(self, code, message, http_status=400, **extra):
        super().__init__(message)
        self.code, self.message, self.http_status, self.extra = code, message, http_status, extra


# ------------------------------------------------------------------ database
def connect(path):
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    path = Path(path)
    if path.exists():
        path.unlink()
    conn = connect(path)
    conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    conn.executescript((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
    conn.commit()
    return conn


def ensure_runtime_db(runtime_path):
    """The app works on a copy, so the published reference database never changes."""
    runtime_path = Path(runtime_path)
    if not runtime_path.exists():
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        if REFERENCE_DATABASE.exists():
            shutil.copyfile(REFERENCE_DATABASE, runtime_path)
        else:
            init_db(runtime_path).close()
    return connect(runtime_path)


def _now(now=None):
    return (now or datetime.now()).isoformat(timespec="seconds")


def audit(conn, event_type, actor, now=None, write_log=True, **fields):
    clean = sanitize(fields)
    cols = {k: clean.pop(k, None) for k in ("entity_type", "entity_id", "document_id", "format",
                                            "processing_status", "provider", "latency_ms",
                                            "error_code")}
    conn.execute(
        "INSERT INTO audit_events (event_time, event_type, actor, entity_type, entity_id, document_id,"
        " format, processing_status, provider, latency_ms, error_code, details)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (_now(now), event_type, actor, cols["entity_type"], cols["entity_id"], cols["document_id"],
         cols["format"], cols["processing_status"], cols["provider"], cols["latency_ms"],
         cols["error_code"], json.dumps(clean) if clean else None))
    if write_log:
        log_event(event_type, actor=actor, **{k: v for k, v in cols.items() if v is not None}, **clean)


def _replay_flags():
    flags = sorted(bug_replay.active())
    return ",".join(flags) or None


# ------------------------------------------------------------------ upload + AI extraction
def process_upload(conn, content, filename, actor="demo_user", now=None, sample_variant="upload",
                   storage_path=None, save_upload=False, providers=None, simulate=None,
                   ground_truth=None, latency_ms=None, category_latency_ms=None, retry_of=None,
                   document_role="primary", case_id=None, write_log=True):
    providers = providers or build_chain()
    res = extract_document(content, filename, providers=providers, simulate=simulate)
    ts = _now(now)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
    ing = res.get("ingestion") or {}

    if save_upload and res["status"] != "rejected":
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}.{ing.get('format') or 'bin'}"
        target.write_bytes(content)
        try:
            storage_path = target.relative_to(ROOT).as_posix()
        except ValueError:  # upload folder configured outside the repository
            storage_path = str(target)

    cur = conn.execute(
        "INSERT INTO documents (case_id, filename, declared_extension, detected_format, sample_variant,"
        " document_role, byte_size, pages, sha256, text_quality, ingestion_status, rejection_code,"
        " storage_path, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (case_id, _safe_name(filename), ext, ing.get("format"), sample_variant, document_role,
         len(content), ing.get("pages"), ing.get("sha256") or _sha(content), ing.get("text_quality"),
         "rejected" if res["status"] == "rejected" else "accepted",
         res.get("error_code") if res["status"] == "rejected" else None,
         storage_path if res["status"] != "rejected" else None, actor, ts))
    document_id = cur.lastrowid
    audit(conn, "document_uploaded", actor, now, write_log, entity_type="document",
          entity_id=document_id, document_id=document_id, format=ing.get("format") or ext,
          byte_size=len(content), processing_status=res["status"])

    if res["status"] == "rejected":
        audit(conn, "file_rejected", actor, now, write_log, entity_type="document",
              entity_id=document_id, document_id=document_id, format=ext,
              processing_status="rejected", error_code=res["error_code"])
        conn.commit()
        return {"status": "rejected", "document_id": document_id, "error_code": res["error_code"],
                "message": res["message"]}

    simulated = latency_ms is not None
    processing_ms = latency_ms if simulated else res["processing_ms"]
    result = res.get("result") or {}
    cur = conn.execute(
        "INSERT INTO ai_runs (document_id, case_id, task, provider_requested, provider_used,"
        " fallback_used, fallback_reason, status, error_stage, error_code, confidence_score,"
        " intake_status, missing_count, conflict_count, processing_ms, latency_is_simulated,"
        " retry_of_run_id, bug_replay, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (document_id, case_id, "extraction", providers[0].name, res.get("provider_used"),
         int(res.get("fallback_used", False)), res.get("fallback_reason"), res["status"],
         res.get("error_stage"), res.get("error_code"), result.get("confidence_score"),
         result.get("case_status"),
         len(result["missing_fields"]) if result else None,
         len(result["conflicts"]) if result else None,
         processing_ms, int(simulated), retry_of, _replay_flags(), ts))
    run_id = cur.lastrowid

    if res["status"] == "error":
        audit(conn, "ai_extraction_failed", actor, now, write_log, entity_type="ai_run",
              entity_id=run_id, document_id=document_id, format=ing.get("format"),
              processing_status="error", error_code=res["error_code"], latency_ms=processing_ms,
              fallback_used=res.get("fallback_used"))
        conn.commit()
        return {"status": "error", "document_id": document_id, "ai_run_id": run_id,
                "error_code": res["error_code"], "error_stage": res.get("error_stage"),
                "message": res.get("message"), "attempts": res.get("attempts", []),
                "fallback_used": res.get("fallback_used", False)}

    conflict_fields = {c["field"] for c in result["conflicts"]}
    for name in SCORED_FIELDS:
        value = result.get(name)
        expected = ground_truth.get(name) if ground_truth is not None else None
        conn.execute(
            "INSERT INTO extracted_fields (ai_run_id, field_name, ai_value, confidence, method,"
            " is_missing, has_conflict, expected_value, is_correct) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, name, to_storage(name, value), result["field_confidence"].get(name, 0.0),
             result["field_method"].get(name), int(to_storage(name, value) is None),
             int(name in conflict_fields), to_storage(name, expected),
             None if ground_truth is None else int(is_correct(name, value, expected))))

    cat = res["category_run"]
    conn.execute(
        "INSERT INTO ai_runs (document_id, case_id, task, provider_requested, provider_used,"
        " fallback_used, fallback_reason, status, error_code, confidence_score, processing_ms,"
        " latency_is_simulated, bug_replay, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (document_id, case_id, "category_suggestion", providers[0].name, cat["provider_used"],
         int(cat["fallback_used"]), cat["fallback_reason"], cat["status"],
         None if cat["status"] == "success" else "AI_UNAVAILABLE",
         result["field_confidence"].get("case_category") if cat["status"] == "success" else None,
         category_latency_ms if category_latency_ms is not None else
         sum(a["latency_ms"] for a in cat["attempts"]),
         int(category_latency_ms is not None), _replay_flags(), ts))

    if res["fallback_used"]:
        audit(conn, "provider_fallback_used", actor, now, write_log, entity_type="ai_run",
              entity_id=run_id, document_id=document_id, provider=res["provider_used"],
              fallback_reason=res["fallback_reason"])
    audit(conn, "ai_extraction_completed", actor, now, write_log, entity_type="ai_run",
          entity_id=run_id, document_id=document_id, format=ing["format"], processing_status="success",
          provider=res["provider_used"], latency_ms=processing_ms,
          confidence_score=result["confidence_score"], case_status=result["case_status"],
          missing_count=len(result["missing_fields"]), conflict_count=len(result["conflicts"]))
    conn.commit()
    return {"status": "success", "document_id": document_id, "ai_run_id": run_id,
            "provider_used": res["provider_used"], "fallback_used": res["fallback_used"],
            "fallback_reason": res["fallback_reason"], "attempts": res["attempts"],
            "ingestion": ing, "result": result, "notice": res["notice"],
            "processing_ms": processing_ms}


def _safe_name(filename):
    name = Path(filename).name
    return name[:120] or "unnamed"


def _sha(content):
    import hashlib
    return hashlib.sha256(content).hexdigest()


# ------------------------------------------------------------------ review draft
def get_run(conn, ai_run_id):
    run = conn.execute(
        "SELECT r.*, d.filename, d.detected_format, d.pages, d.byte_size, d.storage_path,"
        " d.text_quality, d.sample_variant FROM ai_runs r JOIN documents d USING (document_id)"
        " WHERE r.ai_run_id = ? AND r.task = 'extraction'", (ai_run_id,)).fetchone()
    if not run:
        raise ServiceError("RUN_NOT_FOUND", "Extraction run not found.", 404)
    rows = conn.execute("SELECT * FROM extracted_fields WHERE ai_run_id = ? ORDER BY field_id",
                        (ai_run_id,)).fetchall()
    fields = {r["field_name"]: {
        "value": from_storage(r["field_name"], r["ai_value"]),
        "final_value": None if r["was_corrected"] is None else from_storage(r["field_name"], r["final_value"]),
        "confidence": r["confidence"], "method": r["method"], "is_missing": bool(r["is_missing"]),
        "has_conflict": bool(r["has_conflict"]), "was_corrected": r["was_corrected"]} for r in rows}
    values = {k: v["value"] for k, v in fields.items()}
    missing, issues = check_fields(values, [{"field": k} for k, v in fields.items() if v["has_conflict"]])
    return {"run": dict(run), "fields": fields, "missing_fields": missing, "issues": issues}


# ------------------------------------------------------------------ human validation + case
REQUIRED_TO_CREATE = ("case_reference", "case_title", "client_name", "case_category")


def reference_key(reference):
    return "".join(ch for ch in (reference or "").upper() if ch.isalnum())


def create_case(conn, ai_run_id, fields, validated, reviewer="reviewer_demo", idempotency_key=None,
                now=None, review_seconds=None, is_simulated=False, write_log=True):
    replay = bug_replay.is_on("duplicate_no_idempotency")
    if not validated:
        raise ServiceError("VALIDATION_REQUIRED",
                           "A human must review and confirm the fields before a case is created.", 400)
    draft = get_run(conn, ai_run_id)
    run = draft["run"]
    if run["status"] != "success":
        raise ServiceError("RUN_NOT_REVIEWABLE", "This extraction failed; nothing to validate.", 409)

    if not replay:
        if idempotency_key:
            existing = conn.execute("SELECT case_id FROM cases WHERE idempotency_key = ?",
                                    (idempotency_key,)).fetchone()
            if existing:  # same submission received twice (double click, network retry)
                audit(conn, "duplicate_submission_ignored", reviewer, now, write_log, entity_type="case",
                      entity_id=existing["case_id"], ai_run_id=ai_run_id)
                conn.commit()
                return {"status": "existing", "case_id": existing["case_id"]}
        if run["case_id"]:
            raise ServiceError("ALREADY_CREATED", "A case was already created from this extraction.",
                               409, case_id=run["case_id"])

    missing_required = [f for f in REQUIRED_TO_CREATE if not fields.get(f)]
    if missing_required:
        raise ServiceError("MISSING_REQUIRED", "Complete the required fields before creating the case.",
                           422, fields=missing_required)

    ref_key = reference_key(fields["case_reference"])
    if not replay:
        dup = conn.execute("SELECT case_id FROM cases WHERE reference_key = ?", (ref_key,)).fetchone()
        if dup:
            audit(conn, "duplicate_case_blocked", reviewer, now, write_log, entity_type="case",
                  entity_id=dup["case_id"], document_id=run["document_id"], duplicate_of=dup["case_id"])
            conn.commit()
            raise ServiceError("DUPLICATE_CASE", "A case with this reference already exists.", 409,
                               case_id=dup["case_id"])

    ts = _now(now)
    corrections = []
    for name in SCORED_FIELDS:
        ai_value = draft["fields"][name]["value"] if name in draft["fields"] else None
        final = fields.get(name, ai_value)
        if canonical(name, final) != canonical(name, ai_value):
            corrections.append((name, ai_value, final, draft["fields"].get(name, {}).get("has_conflict")))

    final_values = {n: fields.get(n, draft["fields"].get(n, {}).get("value")) for n in SCORED_FIELDS}
    missing_after, _ = check_fields(final_values, [])
    cur = conn.execute(
        "INSERT INTO cases (case_reference, reference_key, title, client_name, opposing_party, category,"
        " jurisdiction, document_type, important_dates, amounts, missing_fields, status, intake_status,"
        " source_document_id, source_ai_run_id, ai_confidence, human_review_status, idempotency_key,"
        " created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fields["case_reference"].strip(), None if replay else ref_key, fields["case_title"].strip(),
         fields["client_name"].strip(), final_values["opposing_party"] or None, fields["case_category"],
         final_values["jurisdiction"] or None, final_values["document_type"] or None,
         to_storage("important_dates", final_values["important_dates"]),
         to_storage("amounts", final_values["amounts"]), json.dumps(missing_after),
         "Awaiting information" if missing_after else "Open", run["intake_status"],
         run["document_id"], ai_run_id, run["confidence_score"],
         "Approved with corrections" if corrections else "Approved",
         None if replay else idempotency_key, reviewer, ts, ts))
    case_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO human_reviews (case_id, ai_run_id, reviewer, review_type, decision, fields_reviewed,"
        " fields_corrected, category_changed, review_seconds, is_simulated, reviewed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (case_id, ai_run_id, reviewer, "intake_validation",
         "Approved with corrections" if corrections else "Approved", len(SCORED_FIELDS),
         len(corrections), int(any(c[0] == "case_category" for c in corrections)), review_seconds,
         int(is_simulated), ts))
    review_id = cur.lastrowid

    corrected_names = {c[0] for c in corrections}
    for name in SCORED_FIELDS:
        conn.execute("UPDATE extracted_fields SET final_value = ?, was_corrected = ?, review_id = ?"
                     " WHERE ai_run_id = ? AND field_name = ?",
                     (to_storage(name, final_values[name]), int(name in corrected_names), review_id,
                      ai_run_id, name))
    for name, ai_value, final, had_conflict in corrections:
        conn.execute("INSERT INTO ai_feedback (ai_run_id, case_id, field_name, feedback_type, comment,"
                     " created_at) VALUES (?,?,?,?,?,?)",
                     (ai_run_id, case_id, name, _feedback_type(name, ai_value, final, had_conflict),
                      "reviewer correction at intake", ts))

    conn.execute("UPDATE documents SET case_id = ? WHERE document_id = ?", (case_id, run["document_id"]))
    conn.execute("UPDATE ai_runs SET case_id = ? WHERE document_id = ?", (case_id, run["document_id"]))
    audit(conn, "human_review_submitted", reviewer, now, write_log, entity_type="case", entity_id=case_id,
          ai_run_id=ai_run_id, fields_reviewed=len(SCORED_FIELDS), fields_corrected=len(corrections))
    audit(conn, "case_created", reviewer, now, write_log, entity_type="case", entity_id=case_id,
          document_id=run["document_id"], processing_status="Awaiting information" if missing_after else "Open")
    conn.commit()
    return {"status": "created", "case_id": case_id, "fields_corrected": len(corrections),
            "corrected_fields": sorted(corrected_names)}


def _feedback_type(name, ai_value, final, had_conflict):
    if had_conflict:
        return "conflict_resolved"
    if name == "case_category":
        return "wrong_category"
    if canonical(name, ai_value) is None:
        return "missing_value"
    if canonical(name, final) is None:
        return "false_positive"
    return "wrong_value"


CASE_EDITABLE = {"title": "case_title", "client_name": "client_name", "opposing_party": "opposing_party",
                 "category": "case_category", "jurisdiction": "jurisdiction", "status": None}


def update_case(conn, case_id, changes, reviewer="reviewer_demo", now=None, write_log=True):
    case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if not case:
        raise ServiceError("CASE_NOT_FOUND", "Case not found.", 404)
    applied = {k: v for k, v in changes.items() if k in CASE_EDITABLE and v != case[k]}
    if not applied:
        return {"status": "unchanged", "case_id": case_id}
    ts = _now(now)
    sets = ", ".join(f"{k} = ?" for k in applied)
    conn.execute(f"UPDATE cases SET {sets}, updated_at = ? WHERE case_id = ?",
                 (*applied.values(), ts, case_id))
    field_changes = {CASE_EDITABLE[k]: v for k, v in applied.items() if CASE_EDITABLE[k]}
    cur = conn.execute(
        "INSERT INTO human_reviews (case_id, ai_run_id, reviewer, review_type, decision, fields_reviewed,"
        " fields_corrected, category_changed, is_simulated, reviewed_at) VALUES (?,?,?,?,?,?,?,?,0,?)",
        (case_id, case["source_ai_run_id"], reviewer, "post_creation_edit",
         "Approved with corrections" if field_changes else "Approved", len(applied), len(field_changes),
         int("category" in applied), ts))
    for name, value in field_changes.items():
        conn.execute("UPDATE extracted_fields SET final_value = ?, was_corrected = 1, review_id = ?"
                     " WHERE ai_run_id = ? AND field_name = ?",
                     (value, cur.lastrowid, case["source_ai_run_id"], name))
    audit(conn, "case_updated", reviewer, now, write_log, entity_type="case", entity_id=case_id,
          fields_corrected=len(field_changes))
    conn.commit()
    return {"status": "updated", "case_id": case_id, "changed": sorted(applied)}


def _case_fields(case):
    return {"case_title": case["title"], "case_reference": case["case_reference"],
            "client_name": case["client_name"], "opposing_party": case["opposing_party"],
            "jurisdiction": case["jurisdiction"], "case_category": case["category"],
            "important_dates": from_storage("important_dates", case["important_dates"]),
            "amounts": from_storage("amounts", case["amounts"]),
            "missing_fields": json.loads(case["missing_fields"] or "[]")}


def _record_task_run(conn, case, task, run, now):
    conn.execute(
        "INSERT INTO ai_runs (document_id, case_id, task, provider_requested, provider_used, fallback_used,"
        " fallback_reason, status, error_code, processing_ms, latency_is_simulated, bug_replay, started_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)",
        (case["source_document_id"], case["case_id"], task, run["attempts"][0]["provider"]
         if run["attempts"] else "none", run["provider_used"], int(run["fallback_used"]),
         run["fallback_reason"], run["status"], run.get("error_code"),
         sum(a["latency_ms"] for a in run["attempts"]), _replay_flags(), _now(now)))


def summarise_case(conn, case_id, now=None, providers=None, simulate=None, write_log=True):
    case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if not case:
        raise ServiceError("CASE_NOT_FOUND", "Case not found.", 404)
    run = generate_case_summary(_case_fields(case), providers=providers, simulate=simulate)
    _record_task_run(conn, case, "summarisation", run, now)
    if run["status"] == "success":
        conn.execute("UPDATE cases SET summary = ?, updated_at = ? WHERE case_id = ?",
                     (run["summary"], _now(now), case_id))
    audit(conn, "summary_generated", "demo_user", now, write_log, entity_type="case", entity_id=case_id,
          processing_status=run["status"], provider=run["provider_used"])
    conn.commit()
    return run


def ask_case(conn, case_id, question, now=None, providers=None, write_log=True):
    case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if not case:
        raise ServiceError("CASE_NOT_FOUND", "Case not found.", 404)
    run = ask(question, _case_fields(case), providers=providers)
    if run.get("attempts"):
        _record_task_run(conn, case, "assistant", run, now)
        # the question text is not stored or logged: only that a question was asked
        audit(conn, "assistant_question", "demo_user", now, write_log, entity_type="case",
              entity_id=case_id, processing_status=run["status"], provider=run["provider_used"])
        conn.commit()
    return run


# ------------------------------------------------------------------ read models for the UI
def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def dashboard(conn):
    kpi = rows(conn, "SELECT * FROM vw_ai_quality_summary")[0]
    return {
        "kpi": kpi,
        "recent_cases": rows(conn, "SELECT case_id, case_reference, title, category, status, intake_status,"
                                   " ai_confidence, human_review_status, created_at FROM cases"
                                   " ORDER BY created_at DESC, case_id DESC LIMIT 8"),
        "recent_runs": rows(conn, "SELECT ai_run_id, document_id, detected_format, provider_used, status,"
                                  " confidence_score, intake_status, processing_ms, started_at"
                                  " FROM vw_extraction_runs ORDER BY started_at DESC, ai_run_id DESC LIMIT 8"),
        "recent_failures": rows(conn, "SELECT r.ai_run_id, r.task, r.error_stage, r.error_code,"
                                      " d.detected_format, r.started_at FROM ai_runs r JOIN documents d"
                                      " USING (document_id) WHERE r.status = 'error'"
                                      " ORDER BY r.started_at DESC, r.ai_run_id DESC LIMIT 6"),
        "monthly": rows(conn, "SELECT substr(started_at,1,7) AS month, COUNT(*) AS runs,"
                              " SUM(status='success') AS successful FROM vw_extraction_runs"
                              " GROUP BY 1 ORDER BY 1"),
    }


def list_cases(conn, search=None, category=None, status=None, limit=200):
    sql = ("SELECT case_id, case_reference, title, client_name, category, status, intake_status,"
           " ai_confidence, human_review_status, created_at FROM cases WHERE 1=1")
    params = []
    if search:
        sql += " AND (title LIKE ? OR case_reference LIKE ? OR client_name LIKE ?)"
        params += [f"%{search}%"] * 3
    if category:
        sql += " AND category = ?"
        params.append(category)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC, case_id DESC LIMIT ?"
    params.append(int(limit))
    return rows(conn, sql, params)


def case_detail(conn, case_id):
    case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if not case:
        raise ServiceError("CASE_NOT_FOUND", "Case not found.", 404)
    data = dict(case)
    for k in ("important_dates", "amounts", "missing_fields"):
        data[k] = json.loads(case[k]) if case[k] else []
    return {
        "case": data,
        "documents": rows(conn, "SELECT document_id, filename, detected_format, document_role, pages,"
                                " byte_size, sample_variant, uploaded_at FROM documents WHERE case_id = ?"
                                " ORDER BY document_id", (case_id,)),
        "ai_runs": rows(conn, "SELECT ai_run_id, task, provider_used, fallback_used, status, error_code,"
                              " confidence_score, processing_ms, started_at FROM ai_runs WHERE case_id = ?"
                              " ORDER BY ai_run_id", (case_id,)),
        "fields": rows(conn, "SELECT field_name, ai_value, final_value, confidence, method, is_missing,"
                             " has_conflict, was_corrected FROM extracted_fields WHERE ai_run_id = ?"
                             " ORDER BY field_id", (case["source_ai_run_id"],)),
        "reviews": rows(conn, "SELECT * FROM human_reviews WHERE case_id = ? ORDER BY review_id", (case_id,)),
        "audit": rows(conn, "SELECT event_time, event_type, actor, processing_status, provider, error_code"
                            " FROM audit_events WHERE entity_type = 'case' AND entity_id = ?"
                            " ORDER BY event_id", (case_id,)),
    }


def quality(conn):
    return {
        "summary": rows(conn, "SELECT * FROM vw_ai_quality_summary")[0],
        "by_document_type": rows(conn, "SELECT * FROM vw_document_type_performance"
                                       " ORDER BY file_family, detected_format, sample_variant"),
        "by_family": rows(conn, "SELECT file_family, COUNT(*) AS runs,"
                                " ROUND(100.0*SUM(status='success')/COUNT(*),1) AS success_rate_pct,"
                                " ROUND(AVG(CASE WHEN status='success' THEN confidence_score END),3) AS avg_confidence,"
                                " ROUND(AVG(processing_ms),0) AS avg_processing_ms"
                                " FROM vw_extraction_runs GROUP BY 1 ORDER BY 1"),
        "by_field": rows(conn, "SELECT * FROM vw_field_accuracy ORDER BY accuracy_pct"),
        "by_provider": rows(conn, "SELECT COALESCE(provider_used,'none (failed)') AS provider, COUNT(*) AS runs,"
                                  " ROUND(AVG(confidence_score),3) AS avg_confidence"
                                  " FROM vw_extraction_runs GROUP BY 1 ORDER BY 2 DESC"),
        "errors": rows(conn, "SELECT * FROM vw_error_analysis ORDER BY failed_runs DESC"),
        "reviews": rows(conn, "SELECT * FROM vw_human_review_metrics ORDER BY review_month"),
        "feedback": rows(conn, "SELECT feedback_type, field_name, COUNT(*) AS n FROM ai_feedback"
                               " GROUP BY 1, 2 ORDER BY n DESC LIMIT 15"),
    }


def tests_overview(conn):
    runs = rows(conn, "SELECT * FROM vw_test_run_summary ORDER BY test_run_id")
    latest = runs[-1]["test_run_id"] if runs else None
    return {
        "runs": runs,
        "matrix": rows(conn, "SELECT test_run_id, scenario_code, status FROM test_results"
                             " ORDER BY test_run_id, scenario_code"),
        "latest": rows(conn, "SELECT scenario_code, scenario_name, document_format, expected, observed,"
                             " status, failure_category, duration_ms FROM test_results"
                             " WHERE test_run_id = ? ORDER BY scenario_code", (latest,)) if latest else [],
    }


def audit_log(conn, event_type=None, limit=200):
    sql = ("SELECT event_id, event_time, event_type, actor, entity_type, entity_id, document_id, format,"
           " processing_status, provider, latency_ms, error_code, details FROM audit_events")
    params = []
    if event_type:
        sql += " WHERE event_type = ?"
        params.append(event_type)
    sql += " ORDER BY event_id DESC LIMIT ?"
    params.append(int(limit))
    return {"events": rows(conn, sql, params),
            "types": rows(conn, "SELECT event_type, COUNT(*) AS n FROM audit_events GROUP BY 1 ORDER BY 2 DESC")}
