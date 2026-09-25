"""Create the portfolio proofs (proofs/proof_01 ... proof_08) from the REAL app and data.

    python scripts/make_proofs.py

* screenshots of the running demo app (headless Chrome / Edge), on a throw-away copy of the database
* the data model diagram (matplotlib, from the live SQLite schema)
* a bug investigation card and a SQL analysis card rendered from the repository files

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
"""
import base64
import html
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "proofs"
DB = ROOT / "database" / "klavis_ai_demo.sqlite"
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
EDGE_PATHS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
SCALE = 1.5
TMP = Path(tempfile.mkdtemp(prefix="klavis_proofs_"))


def browser():
    for p in EDGE_PATHS:
        if Path(p).exists():
            return p
    raise SystemExit("No Edge/Chrome found: proofs need a headless browser")


def shot(url, name, w=1440, h=1400, wait=7000):
    out = TMP / f"{name}.png"
    subprocess.run([browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={TMP / ('prof_' + name)}", f"--window-size={w},{h}",
                    f"--force-device-scale-factor={SCALE}", f"--virtual-time-budget={wait}",
                    f"--screenshot={out}", url], timeout=180, capture_output=True)
    if not out.exists():
        raise RuntimeError(f"screenshot failed: {name}")
    return Image.open(out).convert("RGB")


def crop(img, box):
    return img.crop(tuple(int(v * SCALE) for v in box))


def save(img, name, max_w=2000):
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
    img.save(PROOFS / name, optimize=True)
    print(f"  {name}: {img.width}x{img.height}")


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ------------------------------------------------------------------ app screenshots
def app_proofs():
    runtime = TMP / "runtime.sqlite"
    shutil.copyfile(DB, runtime)
    env = {**os.environ, "LEXLAU_DATABASE": str(runtime), "LEXLAU_PORT": str(PORT),
           "LEXLAU_LOG_PATH": str(TMP / "app.log"), "PYTHONPATH": str(ROOT)}
    server = subprocess.Popen([sys.executable, "-m", "app.backend.server"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if call("/api/health")["status"] == "ok":
                    break
            except OSError:
                time.sleep(0.5)
        gt = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))["samples"]

        # reference numbers first (before the demo actions below add runs)
        img = shot(f"{BASE}/#/tests", "p04", h=1560)
        save(crop(img, (224, 36, 1440, 1540)), "proof_04_test_suite.png")
        img = shot(f"{BASE}/#/quality", "p06", h=1250)
        save(crop(img, (224, 36, 1440, 1250)), "app_ai_quality_page.png")
        img = shot(f"{BASE}/#/dashboard", "dash", h=1210)
        save(crop(img, (0, 0, 1440, 1210)), "app_dashboard.png")

        # proof 01: a synthetic scanned document and its structured extraction
        run1 = call("/api/extract", {"sample": "03_clean_scanned_contract_letter.png"})["ai_run_id"]
        img = shot(f"{BASE}/#/extraction/{run1}", "p01", h=1330)
        save(crop(img, (224, 36, 1440, 1330)), "proof_01_ai_extraction.png")

        # proof 02: degraded photo -> flags -> human corrections -> validated case
        r2 = call("/api/extract", {"sample": "04_degraded_phone_photo.jpg"})
        run2 = r2["ai_run_id"]
        review = shot(f"{BASE}/#/extraction/{run2}", "p02a", h=1450)
        exp = gt["samples/04_degraded_phone_photo.jpg"]["expected"]
        fields = {k: exp[k] for k in ("case_title", "case_reference", "client_name", "opposing_party",
                                      "document_type", "jurisdiction", "important_dates", "amounts",
                                      "case_category")}
        case = call("/api/cases", {"ai_run_id": run2, "fields": fields, "validated": True,
                                   "idempotency_key": "proof-02", "reviewer": "reviewer_demo"})
        detail = shot(f"{BASE}/#/case/{case['case_id']}", "p02b", h=1100)
        left = crop(review, (786, 36, 1440, 1450))
        right = crop(detail, (224, 36, 1440, 1100))
        right = right.resize((round(right.width * left.height / right.height), left.height), Image.LANCZOS)
        from PIL import ImageDraw, ImageFont
        head = 70
        canvas = Image.new("RGB", (left.width + right.width + 24, left.height + head), (15, 35, 64))
        canvas.paste(left, (0, head))
        canvas.paste(right, (left.width + 24, head))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("arialbd.ttf", 30)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 18), "1. AI proposes - flags missing fields and low confidence", fill="white", font=font)
        draw.text((left.width + 44, 18), "2. Human corrects and confirms - 3. case persisted with review + audit trail",
                  fill="white", font=font)
        save(canvas, "proof_02_human_validation.png", max_w=2400)

        # extra audit activity: fallback, outage, invalid file, duplicate
        call("/api/extract", {"sample": "01_clean_formal_notice.pdf", "simulate": "primary_down"})
        call("/api/extract", {"sample": "01_clean_formal_notice.pdf", "simulate": "all_down"})
        bad = base64.b64encode(b"MZ\x90\x00" + bytes(500)).decode()
        call("/api/extract", {"filename": "contract_final.docx", "content_base64": bad})
        dup = call("/api/extract", {"sample": "04_degraded_phone_photo.jpg"})
        call("/api/cases", {"ai_run_id": dup["ai_run_id"], "fields": fields, "validated": True,
                            "idempotency_key": "proof-dup"})

        img = shot(f"{BASE}/#/audit", "p08", h=900)
        save(crop(img, (224, 36, 1440, 900)), "proof_08_audit_log.png")
        log_lines = (TMP / "app.log").read_text(encoding="utf-8").splitlines()
        (TMP / "log_excerpt.txt").write_text("\n".join(log_lines[-12:]), encoding="utf-8")
    finally:
        server.terminate()
        server.wait(timeout=20)


# ------------------------------------------------------------------ data model diagram
def data_model():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ("cases", "documents", "ai_runs", "extracted_fields", "human_reviews", "ai_feedback", "test_runs",
               "test_results", "audit_events")}
    boxes = {  # name: (x, y, key columns)
        "cases": (0.5, 5.2, ["case_id PK", "reference_key UNIQUE", "category CHECK", "status / intake_status",
                             "source_document_id FK", "source_ai_run_id FK", "human_review_status",
                             "idempotency_key UNIQUE"]),
        "documents": (4.6, 5.2, ["document_id PK", "case_id FK (null until case)", "detected_format CHECK",
                                 "sample_variant", "sha256", "ingestion_status", "rejection_code",
                                 "storage_path (no text)"]),
        "ai_runs": (8.7, 5.2, ["ai_run_id PK", "document_id FK", "case_id FK", "task CHECK",
                               "provider_used / fallback_used", "status / error_stage / error_code",
                               "confidence_score", "processing_ms", "retry_of_run_id FK"]),
        "extracted_fields": (12.8, 5.2, ["field_id PK", "ai_run_id FK", "field_name CHECK", "ai_value",
                                         "confidence / method", "is_missing / has_conflict",
                                         "expected_value (ground truth)", "is_correct", "final_value / was_corrected",
                                         "review_id FK"]),
        "human_reviews": (0.5, 0.7, ["review_id PK", "case_id FK", "ai_run_id FK", "reviewer (pseudonym)",
                                     "decision", "fields_reviewed / corrected", "review_seconds",
                                     "is_simulated"]),
        "ai_feedback": (4.6, 0.7, ["feedback_id PK", "ai_run_id FK", "case_id FK", "field_name",
                                   "feedback_type CHECK", "comment (fixed vocabulary)"]),
        "test_runs": (8.7, 0.7, ["test_run_id PK", "run_label / code_version", "bug_replay",
                                 "tests_total = passed + failed"]),
        "test_results": (12.8, 0.7, ["result_id PK", "test_run_id FK", "scenario_code (TEST 0xx)",
                                     "expected / observed", "status PASS/FAIL", "failure_category",
                                     "is_regression"]),
    }
    fig, ax = plt.subplots(figsize=(17, 9.2), dpi=130)
    ax.set_xlim(0, 16.6)
    ax.set_ylim(0, 9.6)
    ax.axis("off")
    navy, teal = "#0f2340", "#0d9488"
    W, H_ROW, HEAD = 3.4, 0.30, 0.46
    geo = {}
    for name, (x, y, cols) in boxes.items():
        h = HEAD + H_ROW * len(cols) + 0.1
        top = y + 3.2
        ax.add_patch(FancyBboxPatch((x, top - h), W, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc="white", ec="#cbd5e1", lw=1.2))
        ax.add_patch(FancyBboxPatch((x, top - HEAD), W, HEAD, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc=navy if name != "test_runs" and name != "test_results" else teal, ec="none"))
        ax.text(x + 0.14, top - HEAD / 2, name, color="white", fontsize=12.5, fontweight="bold", va="center")
        ax.text(x + W - 0.12, top - HEAD / 2, f"{counts[name]:,} rows", color="#cbd5e1", fontsize=9, va="center",
                ha="right")
        for i, c in enumerate(cols):
            ax.text(x + 0.14, top - HEAD - 0.2 - i * H_ROW, c, fontsize=9.6, va="center",
                    color=navy if ("PK" in c or "FK" in c) else "#334155",
                    fontweight="bold" if "PK" in c else "normal")
        geo[name] = (x, top - h, top)
    arrows = [("cases", "documents", "1 : N"), ("documents", "ai_runs", "1 : N"),
              ("ai_runs", "extracted_fields", "1 : N"), ("test_runs", "test_results", "1 : N")]
    for a, b, label in arrows:
        xa, ya0, ya1 = geo[a]
        xb, yb0, yb1 = geo[b]
        y = (max(ya0, yb0) + min(ya1, yb1)) / 2 + 0.6
        ax.annotate("", xy=(xb, y), xytext=(xa + W, y),
                    arrowprops=dict(arrowstyle="-|>", color=teal, lw=2))
        ax.text((xa + W + xb) / 2, y + 0.16, label, ha="center", fontsize=9.5, color=teal, fontweight="bold")
    for a, b, label in [("cases", "human_reviews", "1 : N"), ("ai_runs", "ai_feedback", "1 : N")]:
        xa, ya0, _ = geo[a]
        xb, _, yb1 = geo[b]
        xm = xa + W / 2 if a == "cases" else xb + W / 2
        ax.annotate("", xy=(xb + W / 2 if a == "cases" else xb + W * 0.75, yb1),
                    xytext=(xa + W / 2 if a == "cases" else xa + W * 0.25, ya0),
                    arrowprops=dict(arrowstyle="-|>", color=teal, lw=2, connectionstyle="arc3,rad=0"))
        ax.text(xm + 0.15, (ya0 + yb1) / 2, label, fontsize=9.5, color=teal, fontweight="bold")
    ax.text(0.5, 9.35, "Klavis AI Workflow Demo - relational model (SQLite)", fontsize=17, fontweight="bold",
            color=navy)
    ax.text(0.5, 8.98, "Keys, CHECK rules and UNIQUE guards enforced by sql/schema.sql  |  + audit_events "
            f"({counts['audit_events']:,} rows, metadata only)  |  6 reporting views in sql/views.sql",
            fontsize=10.5, color="#475569")
    ax.text(0.5, 0.18, "Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data "
            "is included. Independently designed schema, not the Klavis production schema.",
            fontsize=9, color="#64748b")
    fig.savefig(TMP / "model.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    save(Image.open(TMP / "model.png").convert("RGB"), "proof_03_data_model.png", max_w=2200)


# ------------------------------------------------------------------ HTML cards
CARD_CSS = """
body{margin:0;background:#f4f6f9;font:15px/1.5 'Segoe UI',Arial,sans-serif;color:#1c2736}
.wrap{padding:28px 32px;width:1336px}
h1{margin:0 0 4px;color:#0f2340;font-size:24px} .sub{color:#64748b;margin:0 0 18px}
.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.step{background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(15,35,64,.06)}
.step h3{margin:0 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#0d9488}
.step p{margin:0;font-size:13.5px}
.step.bad h3{color:#b91c1c} .step.ok h3{color:#15803d}
code{font-family:Consolas,monospace;font-size:12.5px;background:#eef2f7;padding:1px 5px;border-radius:4px}
pre{background:#0f1b2d;color:#d6e2f0;padding:16px 18px;border-radius:10px;font:13px/1.45 Consolas,monospace;margin:0;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;font-size:14px}
th{background:#0f2340;color:#fff;text-align:left;padding:8px 12px;font-weight:600}
td{padding:8px 12px;border-bottom:1px solid #eef1f5} td.n{text-align:right;font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
.foot{margin-top:16px;color:#64748b;font-size:12px}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:700}
.pass{background:#e8f6ee;color:#15803d}.fail{background:#fdecec;color:#b91c1c}
.lab{font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin:0 0 6px}
"""


def render_card(name, body, h):
    page = TMP / f"{name}.html"
    page.write_text(f"<!doctype html><meta charset='utf-8'><style>{CARD_CSS}</style><div class='wrap'>{body}</div>",
                    encoding="utf-8")
    return shot(page.as_uri(), name, w=1400, h=h, wait=1500)


def bug_card():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    before = conn.execute("SELECT COUNT(*), SUM(error_code='PARSE_ERROR') FROM vw_extraction_runs"
                          " WHERE detected_format='docx' AND started_at < '2026-02-16T09:00:00'").fetchone()
    after = conn.execute("SELECT COUNT(*), SUM(error_code='PARSE_ERROR') FROM vw_extraction_runs"
                         " WHERE detected_format='docx' AND started_at >= '2026-02-16T09:00:00'").fetchone()
    runs = conn.execute("SELECT test_run_id, code_version, tests_passed, tests_total, "
                        "(SELECT status FROM test_results r WHERE r.test_run_id=t.test_run_id AND scenario_code='TEST 002'),"
                        "(SELECT status FROM test_results r WHERE r.test_run_id=t.test_run_id AND scenario_code='TEST 013')"
                        " FROM test_runs t ORDER BY test_run_id").fetchall()
    steps = [
        ("Symptom", "", "Every DOCX upload ends in <code>PARSE_ERROR</code>; PDF and images are fine."),
        ("Reproduction", "", "<code>LEXLAU_BUG_REPLAY=docx_routing</code>, upload <code>02_employment_letter.docx</code>: "
                             "fails 3/3 times. TEST 002, 013, 014 fail."),
        ("Observed vs expected", "bad", "Observed: text stage fails, no fields.<br>Expected: DOCX text extracted, "
                                        "9/9 fields like the PDF of the same case."),
        ("Hypothesis", "", "The file reaches the wrong parser: the error comes from <code>pypdf</code>, not from the "
                           "DOCX reader."),
        ("Root cause", "bad", "Routing used an extension table where <code>.docx</code> was missing (only "
                              "<code>.doc</code>), so the default route sent it to the PDF parser."),
        ("Fix", "ok", "Route on the <b>content</b> (magic bytes + <code>word/document.xml</code>), never on the "
                      "file name. Extension mismatch becomes a warning."),
        ("Retest", "ok", f"Unit + scenario tests green. In the dataset: DOCX <code>PARSE_ERROR</code> <b>{before[1]}/{before[0]}</b> "
                         f"before the fix, <b>{after[1] or 0}/{after[0]}</b> after (SQL Q03)."),
        ("Final status", "ok", "Closed after review. A later merge re-introduced it (run #5): caught by TEST 002/013/014 "
                               "as a <b>regression</b>, reverted the same day."),
    ]
    flow = "".join(f"<div class='step {k}'><h3>{i + 1}. {t}</h3><p>{b}</p></div>" for i, (t, k, b) in enumerate(steps))
    rows = "".join(f"<tr><td>#{r[0]}</td><td>{r[1]}</td><td class='n'>{r[2]}/{r[3]}</td>"
                   f"<td><span class='pill {r[4].lower()}'>{r[4]}</span></td>"
                   f"<td><span class='pill {r[5].lower()}'>{r[5]}</span></td></tr>" for r in runs)
    body = (f"<h1>BUG-01 - DOCX routed to the PDF parser</h1><p class='sub'>Synthetic bug reproduced on purpose "
            f"(docs/BUG_INVESTIGATION_CASES.md). Method: symptom &rarr; reproduction &rarr; root cause &rarr; fix "
            f"&rarr; retest &rarr; review.</p><div class='flow'>{flow}</div>"
            f"<div class='grid2' style='margin-top:18px'><div><p class='lab'>Regression test (tests/unit/test_ingestion.py)</p>"
            f"<pre>def test_bug01_replay_routes_docx_to_pdf_parser(self):\n    content = (FIX / \"clean_letter.docx\").read_bytes()\n"
            f"    with bug_replay(\"docx_routing\"), self.assertRaises(IngestionError) as ctx:\n"
            f"        ingest(content, \"letter.docx\")\n    self.assertEqual(ctx.exception.code, \"PARSE_ERROR\")\n"
            f"    self.assertEqual(ingest(content, \"letter.docx\").format, \"docx\")  # fixed</pre></div>"
            f"<div><p class='lab'>Test runs (TEST 002 DOCX / TEST 013 mixed formats)</p><table><tr><th>Run</th><th>Version</th>"
            f"<th>Suite</th><th>TEST 002</th><th>TEST 013</th></tr>{rows}</table></div></div>"
            f"<p class='foot'>These scenarios reproduce the type of AI workflow issues investigated during the professional "
            f"experience, using fully synthetic implementations. Not a Klavis production bug. Synthetic demonstration data.</p>")
    img = render_card("bug", body, 1000)
    save(crop(img, (0, 0, 1400, 1000)).crop((0, 0, int(1400 * SCALE), _content_height(img))), "proof_05_bug_investigation.png")


def _content_height(img):
    """Last non-background row (the card pages have a flat background)."""
    px = img.load()
    bg = px[5, img.height - 5]
    for y in range(img.height - 1, 0, -4):
        row = [px[x, y] for x in range(0, img.width, 25)]
        if any(abs(sum(p) - sum(bg)) > 12 for p in row):
            return min(img.height, y + int(24 * SCALE))
    return img.height


def sql_card():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    text = (ROOT / "sql" / "analysis_queries.sql").read_text(encoding="utf-8")

    def block(code):
        start = text.index(f"-- {code} ")
        end = text.index("-- Q", start + 5)
        chunk = text[start:end].strip()
        title, sql = chunk.split("\n", 1)
        return title[3:], sql.strip()

    parts = []
    for code in ("Q06", "Q03"):
        title, sql = block(code)
        cur = conn.execute(sql.rstrip(";"))
        cols = [d[0] for d in cur.description]
        data = cur.fetchall()
        table = "<table><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>" + "".join(
            "<tr>" + "".join(f"<td class='{'n' if isinstance(v, (int, float)) else ''}'>{html.escape(str(v))}</td>"
                             for v in row) + "</tr>" for row in data) + "</table>"
        parts.append(f"<div><p class='lab'>{html.escape(title)}</p><pre>{html.escape(sql)}</pre>"
                     f"<p class='lab' style='margin-top:12px'>Result (database/klavis_ai_demo.sqlite)</p>{table}</div>")
    body = ("<h1>SQL analysis - is AI confidence a useful signal, and did the fix work?</h1>"
            "<p class='sub'>Two of the 26 queries in <code>sql/analysis_queries.sql</code>, executed on the demo "
            "database (all results: docs/SQL_ANALYSIS_RESULTS.md).</p>"
            f"<div class='grid2'>{parts[0]}{parts[1]}</div>"
            "<p class='foot'>Reading: runs with confidence &ge; 0.90 have 98% field accuracy, runs below 0.70 only 54% "
            "- confidence is a good routing signal for human review. DOCX success went from 0% to 99% after the "
            "routing fix. Synthetic demonstration data.</p>")
    img = render_card("sql", body, 1000)
    save(img.crop((0, 0, img.width, _content_height(img))), "proof_07_sql_analysis.png")


def dashboard_proof():
    """proof_06 = page 1 of the Power BI report when its screenshot exists (taken in Power BI Desktop),
    otherwise the AI Quality page of the demo app."""
    pbi = ROOT / "powerbi" / "screenshots" / "powerbi_01_ai_quality_overview.png"
    src = pbi if pbi.exists() else PROOFS / "app_ai_quality_page.png"
    shutil.copyfile(src, PROOFS / "proof_06_ai_quality_dashboard.png")
    print(f"  proof_06_ai_quality_dashboard.png <- {src.relative_to(ROOT).as_posix()}")


def main():
    PROOFS.mkdir(exist_ok=True)
    print("Proofs:")
    app_proofs()
    dashboard_proof()
    data_model()
    bug_card()
    sql_card()
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
