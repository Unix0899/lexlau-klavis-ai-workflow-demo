"""Klavis AI Workflow Demo - local JSON API + static frontend (Python standard library only).

    python -m app.backend.server            -> http://127.0.0.1:8765

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
The app works on database/app_runtime.sqlite, a copy of the reference database, so
the published dataset is never modified. Delete the runtime file to reset the demo.
"""
import base64
import binascii
import json
import mimetypes
import os
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ai import bug_replay
from ai.config import (AI_DRAFT_NOTICE, ASSISTANT_NOTICE, CATEGORIES, DATABASE_PATH, DISCLOSURE,
                       MAX_UPLOAD_BYTES, ROOT)
from ai.ingestion import IngestionError, ingest
from ai.registry import build_chain
from ai.safe_logging import log_event
from app.backend import services

FRONTEND = ROOT / "app" / "frontend"
SAMPLES = ROOT / "data" / "synthetic_documents" / "samples"
MAX_BODY = int(MAX_UPLOAD_BYTES * 1.4) + 65_536       # base64 overhead + JSON envelope
SERVABLE_ROOTS = (ROOT / "data" / "synthetic_documents", ROOT / "app_uploads")

LOCK = threading.Lock()
CONN = None


def sample_list():
    gt = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))["samples"]
    out = []
    for p in sorted(SAMPLES.iterdir()):
        note = gt.get(f"samples/{p.name}", {}).get("note", "")
        out.append({"name": p.name, "format": p.suffix[1:], "bytes": p.stat().st_size,
                    "note": re.sub(r"^TEST [0-9 /]+- ", "", note)})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "KlavisDemo/1.0"

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):  # default access log replaced by the redacted logger
        pass

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        data = json.dumps(body, ensure_ascii=False, default=str).encode() if ctype.startswith(
            "application/json") else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)
        self._status = status

    def _error(self, status, code, message, **extra):
        self._send(status, {"status": "error", "error_code": code, "message": message, **extra})

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise services.ServiceError("FILE_TOO_LARGE",
                                        f"Upload refused: the limit is {MAX_UPLOAD_BYTES // 1_048_576} MB.", 413)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise services.ServiceError("BAD_JSON", "Request body is not valid JSON.", 400) from None

    def _route(self, method):
        started = time.perf_counter()
        self._status = 500
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                with LOCK:
                    self._api(method, url.path, parse_qs(url.query))
            elif method == "GET":
                self._static(url.path)
            else:
                self._error(405, "METHOD_NOT_ALLOWED", "Method not allowed.")
        except services.ServiceError as exc:
            self._error(exc.http_status, exc.code, exc.message, **exc.extra)
        except Exception as exc:  # never leak a traceback or document content to the client
            self._error(500, "INTERNAL_ERROR", "Unexpected error; see the server log.")
            log_event("server_error", error_code=type(exc).__name__, path=_path_template(url.path))
        finally:
            log_event("http_request", method=method, path=_path_template(url.path), http_status=self._status,
                      latency_ms=round((time.perf_counter() - started) * 1000, 1))

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")

    # ------------------------------------------------------------ static files
    def _static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (FRONTEND / rel).resolve()
        if not str(target).startswith(str(FRONTEND.resolve())) or not target.is_file():
            target = FRONTEND / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ------------------------------------------------------------ API
    def _api(self, method, path, query):
        conn = CONN
        q = {k: v[0] for k, v in query.items()}
        m = re.fullmatch(r"/api/([a-z]+)(?:/(\d+|[\w.\-]+))?(?:/([a-z]+))?", path)
        if not m:
            return self._error(404, "NOT_FOUND", "Unknown endpoint.")
        res, ident, sub = m.groups()

        if method == "GET" and res == "health":
            return self._send(200, {"status": "ok"})
        if method == "GET" and res == "meta":
            return self._send(200, {"disclosure": DISCLOSURE, "ai_notice": AI_DRAFT_NOTICE,
                                    "assistant_notice": ASSISTANT_NOTICE, "categories": CATEGORIES,
                                    "max_upload_mb": MAX_UPLOAD_BYTES // 1_048_576,
                                    "provider_chain": [p.name for p in build_chain()],
                                    "bug_replay": sorted(bug_replay.active())})
        if method == "GET" and res == "samples" and not ident:
            return self._send(200, sample_list())
        if method == "GET" and res == "samples" and ident:
            f = SAMPLES / Path(ident).name
            if not f.is_file():
                return self._error(404, "NOT_FOUND", "Sample not found.")
            return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        if method == "POST" and res == "extract":
            return self._extract(conn, self._json_body())
        if method == "GET" and res == "runs" and ident:
            return self._send(200, services.get_run(conn, int(ident)))
        if method == "GET" and res == "documents" and ident and sub in ("file", "text"):
            return self._document(conn, int(ident), sub)
        if res == "cases":
            if method == "GET" and not ident:
                return self._send(200, services.list_cases(conn, q.get("search"), q.get("category"),
                                                           q.get("status")))
            if method == "POST" and not ident:
                body = self._json_body()
                if body.get("fields", {}).get("case_category") not in CATEGORIES:
                    return self._error(422, "INVALID_CATEGORY", "Choose a category from the taxonomy.")
                out = services.create_case(conn, int(body.get("ai_run_id") or 0), body.get("fields") or {},
                                           bool(body.get("validated")), _reviewer(body),
                                           body.get("idempotency_key"))
                return self._send(201 if out["status"] == "created" else 200, out)
            if method == "GET" and ident and not sub:
                return self._send(200, services.case_detail(conn, int(ident)))
            if method == "PATCH" and ident:
                changes = self._json_body().get("changes") or {}
                if "category" in changes and changes["category"] not in CATEGORIES:
                    return self._error(422, "INVALID_CATEGORY", "Choose a category from the taxonomy.")
                if "status" in changes and changes["status"] not in ("Open", "Awaiting information", "Closed"):
                    return self._error(422, "INVALID_STATUS", "Unknown status.")
                return self._send(200, services.update_case(conn, int(ident), changes))
            if method == "POST" and ident and sub == "summary":
                return self._send(200, services.summarise_case(conn, int(ident)))
            if method == "POST" and ident and sub == "ask":
                return self._send(200, services.ask_case(conn, int(ident), self._json_body().get("question", "")))
        if method == "GET" and res == "dashboard":
            return self._send(200, services.dashboard(conn))
        if method == "GET" and res == "quality":
            out = services.quality(conn)
            out["confidence_bands"] = services.rows(conn, CONFIDENCE_BANDS_SQL)
            return self._send(200, out)
        if method == "GET" and res == "tests":
            return self._send(200, services.tests_overview(conn))
        if method == "POST" and res == "tests" and sub is None and ident == "run":
            return self._run_tests(conn)
        if method == "GET" and res == "audit":
            return self._send(200, services.audit_log(conn, q.get("event_type")))
        return self._error(404, "NOT_FOUND", "Unknown endpoint.")

    def _extract(self, conn, body):
        simulate = {"primary_down": {"extract": {"mock-primary": "PROVIDER_TIMEOUT"}},
                    "all_down": {"extract": {"mock-primary": "PROVIDER_ERROR",
                                             "mock-fallback": "PROVIDER_TIMEOUT"}}}.get(body.get("simulate"))
        if body.get("sample"):
            f = SAMPLES / Path(body["sample"]).name
            if not f.is_file():
                return self._error(404, "NOT_FOUND", "Sample not found.")
            out = services.process_upload(conn, f.read_bytes(), f.name, actor="demo_user",
                                          sample_variant="upload", storage_path=f.relative_to(ROOT).as_posix(),
                                          simulate=simulate)
        else:
            try:
                content = base64.b64decode(body.get("content_base64") or "", validate=True)
            except (binascii.Error, ValueError):
                return self._error(400, "BAD_UPLOAD", "The file could not be decoded.")
            out = services.process_upload(conn, content, str(body.get("filename") or "upload"),
                                          actor="demo_user", save_upload=True, simulate=simulate)
        status = {"success": 200, "error": 503 if out.get("error_code") == "AI_UNAVAILABLE" else 422,
                  "rejected": 413 if out.get("error_code") == "FILE_TOO_LARGE" else 415}[out["status"]]
        return self._send(status, out)

    def _document(self, conn, document_id, what):
        row = conn.execute("SELECT filename, detected_format, storage_path FROM documents WHERE document_id = ?",
                           (document_id,)).fetchone()
        if not row or not row["storage_path"]:
            return self._error(404, "NOT_FOUND", "Document file not available.")
        f = (ROOT / row["storage_path"]).resolve()
        if not any(str(f).startswith(str(r.resolve())) for r in SERVABLE_ROOTS) or not f.is_file():
            return self._error(404, "NOT_FOUND", "Document file not available.")
        if what == "file":
            ctype = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
                     "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            return self._send(200, f.read_bytes(), ctype.get(row["detected_format"], "application/octet-stream"))
        try:  # text preview for the reviewer's screen only; never stored or logged
            text = ingest(f.read_bytes(), row["filename"]).text
        except IngestionError as exc:
            return self._error(422, exc.code, exc.message)
        return self._send(200, {"text": text[:6000], "truncated": len(text) > 6000})

    def _run_tests(self, conn):
        from tests.e2e.scenarios import record_run, run_suite
        started = datetime.now()
        results = run_suite(tuple(sorted(bug_replay.active())))
        run_id, passed = record_run(conn, results, "manual run from the AI Tests page", "local", "ui",
                                    started.isoformat(timespec="seconds"),
                                    datetime.now().isoformat(timespec="seconds"), bug_replay.active())
        services.audit(conn, "test_run_completed", "demo_user", entity_type="test_run", entity_id=run_id,
                       tests_passed=passed, tests_failed=len(results) - passed)
        conn.commit()
        return self._send(200, {"test_run_id": run_id, "passed": passed, "total": len(results),
                                "results": results})


CONFIDENCE_BANDS_SQL = """
SELECT CASE WHEN e.confidence_score >= 0.90 THEN '>= 0.90' WHEN e.confidence_score >= 0.80 THEN '0.80-0.89'
            WHEN e.confidence_score >= 0.70 THEN '0.70-0.79' ELSE '< 0.70' END AS band,
       COUNT(DISTINCT e.ai_run_id) AS runs,
       ROUND(100.0 * SUM(f.is_correct) / COUNT(f.is_correct), 1) AS field_accuracy_pct
FROM vw_extraction_runs e JOIN extracted_fields f ON f.ai_run_id = e.ai_run_id
WHERE e.status = 'success' GROUP BY band ORDER BY MIN(e.confidence_score) DESC"""


def _reviewer(body):
    r = str(body.get("reviewer") or "reviewer_demo")
    return r if re.fullmatch(r"[a-z_0-9]{3,30}", r) else "reviewer_demo"


def _path_template(path):
    return re.sub(r"/\d+", "/{id}", path)[:80]


def main():
    global CONN
    CONN = services.ensure_runtime_db(DATABASE_PATH)
    host = os.environ.get("LEXLAU_HOST", "127.0.0.1")
    port = int(os.environ.get("LEXLAU_PORT", 8765))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Klavis AI Workflow Demo on http://{host}:{port}  (synthetic data, mock AI by default)")
    if bug_replay.active():
        print("  bug replay ON:", ", ".join(sorted(bug_replay.active())))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
