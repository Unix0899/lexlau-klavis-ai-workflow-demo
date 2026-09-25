/* Klavis AI Workflow Demo - single-page frontend (vanilla JS, no build step).
   Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included. */
"use strict";

const view = document.getElementById("view");
let META = { categories: [], ai_notice: "", assistant_notice: "" };
const FIELD_LABELS = {
  case_title: "Case title", case_reference: "Case reference", client_name: "Client",
  opposing_party: "Opposing party", document_type: "Document type", jurisdiction: "Jurisdiction",
  important_dates: "Important dates", amounts: "Amounts", case_category: "Category",
};
const TEXT_FIELDS = ["case_title", "case_reference", "client_name", "opposing_party", "document_type", "jurisdiction"];
const DATE_LABELS = ["incident_date", "notice_date", "response_deadline", "hearing_date"];
const AMOUNT_LABELS = ["amount_claimed", "late_interest", "contractual_penalty"];

// ------------------------------------------------------------------ helpers
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v === null || v === undefined ? "n/a" : `${Number(v).toFixed(1)}%`);
const fmtMs = (v) => (v === null || v === undefined ? "n/a" : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
const fmtConf = (v) => (v === null || v === undefined ? "n/a" : Number(v).toFixed(2));
const human = (s) => String(s ?? "").replace(/_/g, " ");
const shortTime = (s) => (s ? String(s).replace("T", " ").slice(0, 16) : "");
const confClass = (c) => (c >= 0.85 ? "hi" : c >= 0.7 ? "mid" : "lo");
const money = (v, cur) => (v === null || v === undefined ? "unreadable" : `${cur || "EUR"} ${Number(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

function pill(text, kind) { return `<span class="pill ${kind}">${esc(text)}</span>`; }
function statusPill(s) {
  if (!s) return "";
  const kind = { "Complete": "ok", "Needs Review": "warn", "Missing Information": "bad", "success": "ok", "error": "bad",
    "PASS": "ok", "FAIL": "bad", "Open": "teal", "Awaiting information": "warn", "Closed": "info",
    "Approved": "ok", "Approved with corrections": "warn", "rejected": "bad" }[s] || "info";
  return pill(s, kind);
}
function bar(value, max = 100, kind = "") {
  const w = Math.max(0, Math.min(100, (100 * (value || 0)) / max));
  return `<div class="bar ${kind}"><span style="width:${w}%"></span></div>`;
}
async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  return { ok: res.ok, status: res.status, data };
}
function table(cols, rows, opts = {}) {
  const head = cols.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
  const body = rows.map((r) => {
    const cells = cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.html ? c.html(r) : esc(r[c.key])}</td>`).join("");
    const href = opts.href ? opts.href(r) : null;
    return `<tr${href ? ` class="click" data-href="${esc(href)}"` : ""}>${cells}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table>${head ? `<thead><tr>${head}</tr></thead>` : ""}<tbody>${body || `<tr><td colspan="${cols.length}" class="muted">Nothing yet.</td></tr>`}</tbody></table></div>`;
}
function bindRowLinks(root = view) {
  root.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => { location.hash = tr.dataset.href; }));
}
function kpi(label, value, hint, accent) {
  return `<div class="card kpi ${accent ? "accent" : ""}"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="hint">${hint || ""}</div></div>`;
}
function head(title, sub, right = "") {
  return `<div class="page-head"><div><h1>${esc(title)}</h1><p>${sub}</p></div><div class="row-actions">${right}</div></div>`;
}

// ------------------------------------------------------------------ router
const ROUTES = { dashboard: renderDashboard, new: renderNew, extraction: renderExtraction, cases: renderCases,
  case: renderCase, tests: renderTests, quality: renderQuality, audit: renderAudit };

async function router() {
  const [, page = "dashboard", id] = location.hash.split("/");
  const navKey = page === "case" ? "cases" : page;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === navKey));
  const fn = ROUTES[page] || renderDashboard;
  view.innerHTML = `<p class="muted"><span class="spinner"></span> Loading&hellip;</p>`;
  try { await fn(id); } catch (e) { view.innerHTML = `<div class="notice bad">Could not load this page (${esc(e.message)}).</div>`; }
  view.focus({ preventScroll: true });
}

// ------------------------------------------------------------------ dashboard
async function renderDashboard() {
  const { data } = await api("/api/dashboard");
  const k = data.kpi;
  const maxRuns = Math.max(...data.monthly.map((m) => m.runs), 1);
  const cols = data.monthly.map((m) => {
    const okH = (100 * m.successful) / maxRuns, badH = (100 * (m.runs - m.successful)) / maxRuns;
    return `<div class="col"><span>${m.runs}</span><div class="stackbar" style="height:${okH + badH}%">
      <div class="ok-seg" style="flex:${m.successful}"></div><div class="bad-seg" style="flex:${m.runs - m.successful}"></div></div>
      <span>${esc(m.month)}</span></div>`;
  }).join("");
  view.innerHTML = head("Dashboard", "Document intake assisted by AI, validated by a human. Six months of synthetic activity.",
    `<a class="btn" href="#/new">+ New case</a>`) + `
  <div class="grid g6">
    ${kpi("Cases processed", k.cases_created, `${k.extraction_runs} extraction runs`, true)}
    ${kpi("AI success rate", pct(k.ai_success_rate_pct), `${k.failed_runs} failed runs`, true)}
    ${kpi("Average confidence", fmtConf(k.avg_confidence), "successful extractions", true)}
    ${kpi("Human review rate", pct(k.human_review_rate_pct), "needs review or missing info", true)}
    ${kpi("Test pass rate", pct(k.latest_test_pass_rate_pct), "latest suite run (TEST 001-014)", true)}
    ${kpi("Avg processing time", fmtMs(k.avg_processing_ms), "latency model, see docs", true)}
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h2>AI extraction runs per month</h2>
      <div class="cols">${cols}</div>
      <p class="small muted">Teal = success, red = failed run. The January-February failures are the DOCX routing bug (BUG-01), fixed on 16 Feb 2026.</p></div>
    <div class="card"><h2>Recent failures</h2>${table([
      { label: "Run", key: "ai_run_id" }, { label: "Task", html: (r) => esc(human(r.task)) },
      { label: "Stage", html: (r) => esc(human(r.error_stage || "ai provider")) }, { label: "Error", html: (r) => `<code>${esc(r.error_code)}</code>` },
      { label: "Format", key: "detected_format" }, { label: "When", html: (r) => shortTime(r.started_at) }], data.recent_failures)}
    </div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h2>Recent cases</h2>${table([
      { label: "Reference", html: (r) => `<span class="mono">${esc(r.case_reference)}</span>` },
      { label: "Title", key: "title" }, { label: "Category", key: "category" },
      { label: "Intake", html: (r) => statusPill(r.intake_status) }], data.recent_cases, { href: (r) => `#/case/${r.case_id}` })}</div>
    <div class="card"><h2>Recent AI runs</h2>${table([
      { label: "Run", key: "ai_run_id" }, { label: "Format", key: "detected_format" },
      { label: "Provider", key: "provider_used" }, { label: "Status", html: (r) => statusPill(r.status) },
      { label: "Conf.", num: true, html: (r) => fmtConf(r.confidence_score) },
      { label: "Time", num: true, html: (r) => fmtMs(r.processing_ms) }], data.recent_runs, { href: (r) => `#/extraction/${r.ai_run_id}` })}</div>
  </div>`;
  bindRowLinks();
}

// ------------------------------------------------------------------ new case
async function renderNew() {
  const { data: samples } = await api("/api/samples");
  view.innerHTML = head("New Case", "Upload a document or pick a synthetic sample. The AI proposes, a human validates, then the case is created.") + `
  <div class="grid split">
    <div class="card stack">
      <h2>1. Upload a document</h2>
      <div class="dropzone" id="drop">
        <p><strong>Drop a PDF, DOCX, PNG or JPG here</strong></p>
        <p class="muted small">Maximum ${META.max_upload_mb || 5} MB. Only use synthetic documents: this is a public demo.</p>
        <input type="file" id="file" accept=".pdf,.docx,.png,.jpg,.jpeg">
      </div>
      <div>
        <h3>Resilience demo</h3>
        <label class="check"><input type="radio" name="sim" value="" checked> Normal run</label>
        <label class="check"><input type="radio" name="sim" value="primary_down"> Simulate a primary provider outage (fallback expected)</label>
        <label class="check"><input type="radio" name="sim" value="all_down"> Simulate both providers down (controlled error expected)</label>
      </div>
      <div id="result"></div>
    </div>
    <div class="card"><h2>2. Or try a synthetic sample</h2>
      <div class="samples">${samples.map((s) => `<button class="sample" data-sample="${esc(s.name)}">
        <span class="fmt">${esc(s.format)}</span><strong>${esc(s.name.replace(/^\d+_/, "").replace(/\.\w+$/, "").replace(/_/g, " "))}</strong>
        <span class="small muted">${esc(s.note)}</span></button>`).join("")}</div>
      <p class="small muted" style="margin-top:12px">Every sample is fictional and was generated for this demo (see <code>data/ground_truth.json</code>).</p>
    </div>
  </div>`;
  const sim = () => view.querySelector("input[name=sim]:checked").value || undefined;
  view.querySelectorAll("[data-sample]").forEach((b) => b.addEventListener("click", () => submit({ sample: b.dataset.sample, simulate: sim() })));
  const file = view.querySelector("#file"), drop = view.querySelector("#drop");
  const readFile = (f) => {
    const reader = new FileReader();
    reader.onload = () => submit({ filename: f.name, content_base64: String(reader.result).split(",")[1] || "", simulate: sim() });
    reader.readAsDataURL(f);
  };
  file.addEventListener("change", () => file.files[0] && readFile(file.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });
}

async function submit(body) {
  const box = view.querySelector("#result");
  box.innerHTML = `<p><span class="spinner"></span> Ingesting and extracting&hellip;</p>`;
  view.querySelectorAll("button.sample").forEach((b) => (b.disabled = true));
  const { data } = await api("/api/extract", { method: "POST", body });
  view.querySelectorAll("button.sample").forEach((b) => (b.disabled = false));
  if (data && data.status === "success") { sessionStorage.setItem(`draft-${data.ai_run_id}`, JSON.stringify(data)); location.hash = `#/extraction/${data.ai_run_id}`; return; }
  const attempts = (data && data.attempts || []).map((a) => `${esc(a.provider)}: ${esc(a.error_code || a.status)}`).join(" &rarr; ");
  box.innerHTML = `<div class="notice bad"><strong>${esc(data ? data.error_code : "ERROR")}</strong> &mdash; ${esc(data ? data.message : "Request failed")}
    ${attempts ? `<div class="small">Attempts: ${attempts}</div>` : ""}
    <div class="small">Structured error returned by the API. Nothing was saved as a case${data && data.ai_run_id ? `; failed run #${data.ai_run_id} is recorded for analysis` : ""}.</div></div>`;
}

// ------------------------------------------------------------------ AI extraction + human validation
async function renderExtraction(id) {
  if (!id) {
    const { data } = await api("/api/dashboard");
    view.innerHTML = head("AI Extraction", "Pick a recent extraction to review, or start a new case.", `<a class="btn" href="#/new">+ New case</a>`) +
      `<div class="card">${table([{ label: "Run", key: "ai_run_id" }, { label: "Format", key: "detected_format" }, { label: "Provider", key: "provider_used" },
        { label: "Status", html: (r) => statusPill(r.status) }, { label: "Intake", html: (r) => statusPill(r.intake_status) },
        { label: "Conf.", num: true, html: (r) => fmtConf(r.confidence_score) }, { label: "When", html: (r) => shortTime(r.started_at) }],
        data.recent_runs, { href: (r) => `#/extraction/${r.ai_run_id}` })}</div>`;
    bindRowLinks();
    return;
  }
  const { ok, data: draft } = await api(`/api/runs/${id}`);
  if (!ok) { view.innerHTML = `<div class="notice bad">${esc(draft.message)}</div>`; return; }
  const run = draft.run;
  const fresh = JSON.parse(sessionStorage.getItem(`draft-${id}`) || "null");
  const fields = draft.fields;
  const values = {};
  Object.keys(fields).forEach((k) => (values[k] = JSON.parse(JSON.stringify(fields[k].final_value ?? fields[k].value))));
  const aiValues = {};
  Object.keys(fields).forEach((k) => (aiValues[k] = JSON.stringify(fields[k].value)));
  const idem = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random();
  const locked = Boolean(run.case_id) || run.status !== "success";
  const conf = run.confidence_score || 0;

  view.innerHTML = head(`AI Extraction #${esc(id)}`, `${esc(run.filename)} &middot; ${esc((run.detected_format || "").toUpperCase())} &middot; ${esc(run.pages || 1)} page(s)`,
    `${statusPill(run.intake_status)} ${run.fallback_used ? pill(`fallback: ${run.fallback_reason}`, "warn") : ""}`) + `
  <div class="notice" style="margin-bottom:16px"><strong>${esc(META.ai_notice)}</strong></div>
  <div class="grid split">
    <div class="card"><div class="tabs"><button class="on" data-tab="doc">Document</button><button data-tab="json">Structured JSON</button></div>
      <div id="tab-doc"><div class="doc-preview" id="preview"><span class="spinner"></span></div>
        <p class="small muted">Text shown for the reviewer only. It is not stored in the database and never written to logs.</p></div>
      <div id="tab-json" hidden><pre class="json" id="json"></pre></div>
    </div>
    <div class="stack">
      <div class="card">
        <div class="row-actions" style="justify-content:space-between">
          <div class="gauge"><div class="ring" style="background:conic-gradient(var(--teal) ${conf * 360}deg,#e8edf3 0)"><div style="background:#fff;width:48px;height:48px;border-radius:50%;display:grid;place-items:center">${fmtConf(conf)}</div></div>
            <div><strong>Overall confidence</strong><div class="small muted">mean of 9 field confidences &middot; review threshold 0.80</div></div></div>
          <div class="small muted" style="text-align:right">Provider used: <strong>${esc(run.provider_used || "none")}</strong><br>Processing: ${fmtMs(run.processing_ms)}</div>
        </div>
        ${draft.issues.length ? `<div class="notice ${draft.missing_fields.length ? "bad" : ""}" style="margin-top:12px"><strong>${esc(run.intake_status)}:</strong> ${draft.issues.map(esc).join(" &middot; ")}</div>` : `<div class="notice ok" style="margin-top:12px">All required fields found, no conflict detected. A human still validates before the case is created.</div>`}
      </div>
      <div class="card" id="form"></div>
      <div class="card" id="confirm"></div>
    </div>
  </div>`;

  view.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    view.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
    view.querySelector("#tab-doc").hidden = b.dataset.tab !== "doc";
    view.querySelector("#tab-json").hidden = b.dataset.tab !== "json";
  }));
  const structured = {
    case_title: values.case_title, case_reference: values.case_reference, client_name: values.client_name,
    opposing_party: values.opposing_party, document_type: values.document_type, jurisdiction: values.jurisdiction,
    important_dates: values.important_dates, amounts: values.amounts,
    summary: fresh && fresh.result ? fresh.result.summary : "(generated on the case page)",
    case_category: values.case_category, case_status: run.intake_status, missing_fields: draft.missing_fields,
    confidence_score: run.confidence_score,
    field_confidence: Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.confidence])),
  };
  view.querySelector("#json").textContent = JSON.stringify(structured, null, 2);
  loadPreview(run);

  const form = view.querySelector("#form");
  const renderForm = () => {
    const changed = (k) => JSON.stringify(values[k] ?? null) !== (aiValues[k] === undefined ? "null" : aiValues[k]) && !(values[k] === "" && aiValues[k] === "null");
    const meta = (k) => `<div class="meta"><span class="conf ${confClass(fields[k].confidence)}">${fmtConf(fields[k].confidence)}</span><br>${esc(human(fields[k].method || (fields[k].is_missing ? "not found" : "")))}</div>`;
    const cls = (k) => `field ${fields[k].is_missing ? "missing" : ""} ${fields[k].has_conflict ? "conflict" : ""} ${changed(k) ? "changed" : ""}`;
    const text = TEXT_FIELDS.map((k) => `<div class="${cls(k)}"><div class="name">${FIELD_LABELS[k]}${fields[k].is_missing ? ` ${pill("missing", "bad")}` : ""}${fields[k].has_conflict ? ` ${pill("conflict", "warn")}` : ""}</div>
      <input type="text" data-f="${k}" value="${esc(values[k] ?? "")}" ${locked ? "disabled" : ""} placeholder="not found in the document">${meta(k)}</div>`).join("");
    const cat = `<div class="${cls("case_category")}"><div class="name">${FIELD_LABELS.case_category}</div>
      <select data-f="case_category" ${locked ? "disabled" : ""}><option value="">(choose)</option>${META.categories.map((c) => `<option ${c === values.case_category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>${meta("case_category")}</div>`;
    const dates = (values.important_dates || []).map((d, i) => `<tr><td><select data-d="${i}" data-k="label" ${locked ? "disabled" : ""}>${DATE_LABELS.map((l) => `<option value="${l}" ${l === d.label ? "selected" : ""}>${human(l)}</option>`).join("")}</select></td>
      <td><input type="text" data-d="${i}" data-k="date" value="${esc(d.date || "")}" placeholder="YYYY-MM-DD" ${locked ? "disabled" : ""}></td>
      <td class="small muted">${d.incomplete ? pill("incomplete: " + (d.raw || ""), "warn") : esc(d.raw || "")}</td></tr>`).join("");
    const amounts = (values.amounts || []).map((a, i) => `<tr><td><select data-a="${i}" data-k="label" ${locked ? "disabled" : ""}>${AMOUNT_LABELS.map((l) => `<option value="${l}" ${l === a.label ? "selected" : ""}>${human(l)}</option>`).join("")}</select></td>
      <td><input type="text" data-a="${i}" data-k="value" value="${a.value ?? ""}" ${locked ? "disabled" : ""}></td><td class="small muted">${esc(a.currency || "EUR")} &middot; ${esc(a.raw || "")}</td></tr>`).join("");
    form.innerHTML = `<h2>Proposed fields <span class="small muted">&mdash; edit anything that is wrong</span></h2>${text}${cat}
      <div class="${cls("important_dates")}" style="grid-template-columns:150px 1fr"><div class="name">${FIELD_LABELS.important_dates}${fields.important_dates.has_conflict ? ` ${pill("conflict", "warn")}` : ""}</div>
        <div><table class="mini-table"><tbody>${dates || `<tr><td class="muted">No date found</td></tr>`}</tbody></table>${locked ? "" : `<button data-add="date" class="small">+ add date</button>`}</div></div>
      <div class="${cls("amounts")}" style="grid-template-columns:150px 1fr"><div class="name">${FIELD_LABELS.amounts}${fields.amounts.has_conflict ? ` ${pill("conflict", "warn")}` : ""}</div>
        <div><table class="mini-table"><tbody>${amounts || `<tr><td class="muted">No amount found</td></tr>`}</tbody></table>${locked ? "" : `<button data-add="amount" class="small">+ add amount</button>`}</div></div>`;
    form.querySelectorAll("[data-f]").forEach((el) => el.addEventListener("change", () => { values[el.dataset.f] = el.value.trim() || null; renderForm(); renderConfirm(); }));
    form.querySelectorAll("[data-d]").forEach((el) => el.addEventListener("change", () => {
      const d = values.important_dates[+el.dataset.d]; d[el.dataset.k] = el.value.trim() || null;
      if (el.dataset.k === "date" && d.date) d.incomplete = false; renderForm(); renderConfirm(); }));
    form.querySelectorAll("[data-a]").forEach((el) => el.addEventListener("change", () => {
      const a = values.amounts[+el.dataset.a];
      if (el.dataset.k === "value") { const n = parseFloat(el.value.replace(/[^0-9.\-]/g, "")); a.value = isNaN(n) ? null : n; } else a.label = el.value;
      renderForm(); renderConfirm(); }));
    form.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.add === "date") (values.important_dates = values.important_dates || []).push({ label: "response_deadline", date: null, raw: "added by reviewer", incomplete: false });
      else (values.amounts = values.amounts || []).push({ label: "amount_claimed", value: null, currency: "EUR", raw: "added by reviewer" });
      renderForm(); renderConfirm(); }));
  };

  const confirm = view.querySelector("#confirm");
  const renderConfirm = () => {
    if (run.case_id) { confirm.innerHTML = `<div class="notice ok">Validated by a human. Case <a href="#/case/${run.case_id}">#${run.case_id}</a> was created from this extraction.</div>`; return; }
    if (run.status !== "success") { confirm.innerHTML = `<div class="notice bad">This run failed (${esc(run.error_code)}). Nothing to validate.</div>`; return; }
    const n = Object.keys(values).filter((k) => JSON.stringify(values[k] ?? null) !== aiValues[k]).length;
    confirm.innerHTML = `<h2>3. Human validation</h2>
      <p class="small muted">AI proposes &rarr; <strong>human reviews</strong> &rarr; application persists. ${n} field(s) changed by you.</p>
      <label class="check"><input type="checkbox" id="ack"> I reviewed the proposed fields and confirm them.</label>
      <div class="row-actions" style="margin-top:10px"><button class="primary" id="create" disabled>Confirm &amp; create case</button><span id="create-msg" class="small"></span></div>`;
    const ack = confirm.querySelector("#ack"), btn = confirm.querySelector("#create");
    ack.addEventListener("change", () => (btn.disabled = !ack.checked));
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Creating&hellip;`;
      const { ok, data } = await api("/api/cases", { method: "POST", body: { ai_run_id: Number(id), fields: values, validated: ack.checked, idempotency_key: idem, reviewer: "reviewer_demo" } });
      const msg = confirm.querySelector("#create-msg");
      if (ok) { sessionStorage.removeItem(`draft-${id}`); location.hash = `#/case/${data.case_id}`; return; }
      btn.innerHTML = "Confirm &amp; create case"; btn.disabled = false;
      msg.innerHTML = data.error_code === "DUPLICATE_CASE" || data.error_code === "ALREADY_CREATED"
        ? `<span class="pill bad">Duplicate prevented</span> ${esc(data.message)} <a href="#/case/${data.case_id}">Open case #${data.case_id}</a>`
        : `<span class="pill bad">${esc(data.error_code)}</span> ${esc(data.message)}`;
    });
  };
  renderForm();
  renderConfirm();
}

async function loadPreview(run) {
  const box = view.querySelector("#preview");
  const { ok, data } = await api(`/api/documents/${run.document_id}/text`);
  const text = ok ? esc(data.text) + (data.truncated ? "\n[...]" : "") : `<span class="muted">${esc(data ? data.message : "Preview unavailable")}</span>`;
  if (run.detected_format === "png" || run.detected_format === "jpg") {
    box.innerHTML = `<img src="/api/documents/${run.document_id}/file" alt="Synthetic document image"><h3 style="margin-top:14px">Simulated OCR text layer</h3>${text}`;
  } else {
    box.innerHTML = `${text}<p class="small"><a href="/api/documents/${run.document_id}/file" target="_blank" rel="noopener">Open the original ${esc((run.detected_format || "").toUpperCase())}</a></p>`;
  }
}

// ------------------------------------------------------------------ cases
async function renderCases() {
  const params = new URLSearchParams(sessionStorage.getItem("case-filter") || "");
  const { data } = await api(`/api/cases?${params}`);
  view.innerHTML = head("Cases", `${data.length} case(s) shown. Every case was validated by a (simulated or demo) reviewer before creation.`,
    `<a class="btn" href="#/new">+ New case</a>`) + `
  <div class="card"><div class="row-actions" style="margin-bottom:12px">
    <input type="search" id="q" placeholder="Search reference, title or client" value="${esc(params.get("search") || "")}" style="max-width:320px">
    <select id="cat" style="max-width:220px"><option value="">All categories</option>${META.categories.map((c) => `<option ${c === params.get("category") ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
    <select id="st" style="max-width:200px"><option value="">All statuses</option>${["Open", "Awaiting information", "Closed"].map((s) => `<option ${s === params.get("status") ? "selected" : ""}>${s}</option>`).join("")}</select>
  </div>
  ${table([{ label: "Reference", html: (r) => `<span class="mono">${esc(r.case_reference)}</span>` }, { label: "Title", key: "title" },
    { label: "Client", key: "client_name" }, { label: "Category", key: "category" }, { label: "Status", html: (r) => statusPill(r.status) },
    { label: "Intake", html: (r) => statusPill(r.intake_status) }, { label: "AI conf.", num: true, html: (r) => fmtConf(r.ai_confidence) },
    { label: "Review", html: (r) => statusPill(r.human_review_status) }, { label: "Created", html: (r) => shortTime(r.created_at) }], data, { href: (r) => `#/case/${r.case_id}` })}</div>`;
  bindRowLinks();
  const apply = () => {
    const p = new URLSearchParams();
    const q = view.querySelector("#q").value.trim(), c = view.querySelector("#cat").value, s = view.querySelector("#st").value;
    if (q) p.set("search", q); if (c) p.set("category", c); if (s) p.set("status", s);
    sessionStorage.setItem("case-filter", p.toString()); renderCases();
  };
  view.querySelector("#q").addEventListener("change", apply);
  view.querySelector("#cat").addEventListener("change", apply);
  view.querySelector("#st").addEventListener("change", apply);
}

async function renderCase(id) {
  const { ok, data } = await api(`/api/cases/${id}`);
  if (!ok) { view.innerHTML = `<div class="notice bad">${esc(data.message)}</div>`; return; }
  const c = data.case;
  const fieldRows = data.fields.map((f) => {
    const show = (v) => (v && (f.field_name === "important_dates" || f.field_name === "amounts") ? JSON.parse(v).map((x) => `${human(x.label)}: ${x.date ?? (x.value !== undefined ? money(x.value, x.currency) : x.raw)}`).join("<br>") : esc(v ?? "-"));
    return `<tr><td>${FIELD_LABELS[f.field_name]}</td><td>${show(f.final_value)}</td><td class="small muted">${f.was_corrected ? `AI: ${show(f.ai_value)}` : ""}</td>
      <td><span class="conf ${confClass(f.confidence)}">${fmtConf(f.confidence)}</span></td><td>${f.was_corrected ? pill("corrected", "warn") : f.was_corrected === 0 ? pill("accepted", "ok") : ""}</td></tr>`;
  }).join("");
  view.innerHTML = head(c.title, `<span class="mono">${esc(c.case_reference)}</span> &middot; ${esc(c.client_name)} v. ${esc(c.opposing_party || "(opposing party missing)")}`,
    `${statusPill(c.status)} ${statusPill(c.intake_status)} ${statusPill(c.human_review_status)}`) + `
  <div class="grid split">
    <div class="stack">
      <div class="card"><h2>Case record</h2><dl class="kv">
        <dt>Case ID</dt><dd>#${c.case_id}</dd><dt>Category</dt><dd>${esc(c.category)}</dd><dt>Jurisdiction</dt><dd>${esc(c.jurisdiction || "missing")}</dd>
        <dt>Document type</dt><dd>${esc(c.document_type || "-")}</dd><dt>AI confidence</dt><dd>${fmtConf(c.ai_confidence)}</dd>
        <dt>Missing fields</dt><dd>${c.missing_fields.length ? c.missing_fields.map((m) => pill(human(m), "bad")).join(" ") : "none"}</dd>
        <dt>Created</dt><dd>${shortTime(c.created_at)} by ${esc(c.created_by)}</dd><dt>Updated</dt><dd>${shortTime(c.updated_at)}</dd>
        <dt>Source document</dt><dd><a href="#/extraction/${c.source_ai_run_id}">extraction #${c.source_ai_run_id}</a></dd></dl>
        <div class="row-actions" style="margin-top:12px">
          <select id="edit-cat" style="max-width:220px">${META.categories.map((x) => `<option ${x === c.category ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
          <select id="edit-st" style="max-width:190px">${["Open", "Awaiting information", "Closed"].map((s) => `<option ${s === c.status ? "selected" : ""}>${s}</option>`).join("")}</select>
          <button id="save">Save change</button><span id="save-msg" class="small muted"></span></div></div>
      <div class="card"><h2>Validated fields</h2><div class="table-wrap"><table><thead><tr><th>Field</th><th>Validated value</th><th>AI proposal</th><th>Conf.</th><th></th></tr></thead><tbody>${fieldRows}</tbody></table></div></div>
      <div class="card"><h2>Documents</h2>${table([{ label: "ID", key: "document_id" }, { label: "File", key: "filename" }, { label: "Role", key: "document_role" },
        { label: "Format", key: "detected_format" }, { label: "Variant", key: "sample_variant" }, { label: "Uploaded", html: (r) => shortTime(r.uploaded_at) }], data.documents)}</div>
      <div class="card"><h2>AI runs on this case</h2>${table([{ label: "Run", key: "ai_run_id" }, { label: "Task", html: (r) => human(r.task) }, { label: "Provider", key: "provider_used" },
        { label: "Status", html: (r) => statusPill(r.status) }, { label: "Fallback", html: (r) => (r.fallback_used ? pill("yes", "warn") : "no") }, { label: "Time", num: true, html: (r) => fmtMs(r.processing_ms) }], data.ai_runs)}</div>
    </div>
    <div class="stack">
      <div class="card"><div class="row-actions" style="justify-content:space-between"><h2 style="margin:0">Case summary</h2><button class="primary" id="sum">Generate Case Summary</button></div>
        <div id="summary" style="margin-top:10px">${c.summary ? `<p>${esc(c.summary)}</p>` : `<p class="muted">No summary yet.</p>`}</div>
        <div class="notice">${esc(META.ai_notice)}</div></div>
      <div class="card"><h2>Ask about this case</h2><div class="notice teal" style="margin-bottom:10px"><strong>${esc(META.assistant_notice)}</strong> Answers use the validated fields of this synthetic case only.</div>
        <div class="chat" id="chat"></div>
        <div class="chips" style="margin:10px 0">${["What parties were identified?", "What important dates were detected?", "Which information is still missing?", "Summarise this case."].map((q) => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
        <div class="row-actions"><input type="text" id="question" placeholder="Ask a question about this case" maxlength="500"><button id="ask">Ask</button></div></div>
      <div class="card"><h2>Human reviews</h2>${table([{ label: "Type", html: (r) => human(r.review_type) }, { label: "Reviewer", key: "reviewer" },
        { label: "Decision", html: (r) => statusPill(r.decision) }, { label: "Corrected", num: true, html: (r) => `${r.fields_corrected}/${r.fields_reviewed}` },
        { label: "When", html: (r) => shortTime(r.reviewed_at) }], data.reviews)}</div>
      <div class="card"><h2>Audit trail</h2>${table([{ label: "When", html: (r) => shortTime(r.event_time) }, { label: "Event", html: (r) => `<code>${esc(r.event_type)}</code>` },
        { label: "Actor", key: "actor" }, { label: "Status", key: "processing_status" }], data.audit)}</div>
    </div>
  </div>`;
  const chat = view.querySelector("#chat");
  const ask = async (q) => {
    if (!q) return;
    chat.insertAdjacentHTML("beforeend", `<div class="msg q">${esc(q)}</div>`);
    const { data: r } = await api(`/api/cases/${id}/ask`, { method: "POST", body: { question: q } });
    chat.insertAdjacentHTML("beforeend", `<div class="msg a">${esc(r.answer || r.message)}<div class="small muted">${esc(r.provider_used || "")} &middot; not legal advice</div></div>`);
    chat.scrollTop = chat.scrollHeight;
  };
  view.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.q)));
  view.querySelector("#ask").addEventListener("click", () => { const i = view.querySelector("#question"); ask(i.value.trim()); i.value = ""; });
  view.querySelector("#question").addEventListener("keydown", (e) => { if (e.key === "Enter") view.querySelector("#ask").click(); });
  view.querySelector("#sum").addEventListener("click", async () => {
    const box = view.querySelector("#summary"); box.innerHTML = `<span class="spinner"></span>`;
    const { data: r } = await api(`/api/cases/${id}/summary`, { method: "POST" });
    box.innerHTML = r.status === "success" ? `<p>${esc(r.summary)}</p><p class="small muted">Generated by ${esc(r.provider_used)} from the validated fields.</p>` : `<div class="notice bad">${esc(r.message)}</div>`;
  });
  view.querySelector("#save").addEventListener("click", async () => {
    const { ok: saved, data: r } = await api(`/api/cases/${id}`, { method: "PATCH", body: { changes: { category: view.querySelector("#edit-cat").value, status: view.querySelector("#edit-st").value } } });
    view.querySelector("#save-msg").textContent = saved ? (r.status === "unchanged" ? "No change." : "Saved and recorded as a human review.") : r.message;
    if (saved && r.status !== "unchanged") setTimeout(() => renderCase(id), 600);
  });
}

// ------------------------------------------------------------------ AI tests
async function renderTests() {
  const { data } = await api("/api/tests");
  const runs = data.runs;
  const codes = [...new Set(data.matrix.map((m) => m.scenario_code))];
  const cell = {};
  data.matrix.forEach((m) => (cell[`${m.test_run_id}|${m.scenario_code}`] = m.status));
  const names = Object.fromEntries(data.latest.map((r) => [r.scenario_code, r.scenario_name]));
  view.innerHTML = head("AI Tests", "Scenario suite TEST 001-014, executed on the real workflow. Earlier runs replay the five synthetic bugs until their fix.",
    `<button class="primary" id="run">Run test suite now</button>`) + `
  <div id="run-result"></div>
  <div class="card"><h2>Test runs</h2>${table([{ label: "#", key: "test_run_id" }, { label: "Run", key: "run_label" }, { label: "Version", key: "code_version" },
    { label: "Bug replay", html: (r) => (r.bug_replay ? `<span class="small mono">${r.bug_replay.split(",").map(esc).join("<br>")}</span>` : `<span class="muted">none</span>`) },
    { label: "Passed", num: true, html: (r) => `${r.tests_passed}/${r.tests_total}` }, { label: "Pass rate", html: (r) => `<div style="min-width:120px">${bar(r.pass_rate_pct, 100, r.pass_rate_pct < 100 ? "warn" : "")}</div>` },
    { label: "Regressions", num: true, html: (r) => (r.regressions ? pill(r.regressions, "bad") : "0") }, { label: "Started", html: (r) => shortTime(r.started_at) }], runs)}</div>
  <div class="card" style="margin-top:16px"><h2>Scenario x run matrix</h2><div class="table-wrap"><table class="matrix"><thead><tr><th>Scenario</th>${runs.map((r) => `<th class="num">#${r.test_run_id}</th>`).join("")}</tr></thead>
    <tbody>${codes.map((c) => `<tr><td><strong>${c}</strong> <span class="muted">${esc(names[c] || "")}</span></td>${runs.map((r) => `<td class="${cell[`${r.test_run_id}|${c}`] || ""}">${cell[`${r.test_run_id}|${c}`] || ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
  <div class="card" style="margin-top:16px"><h2>Latest run &mdash; expected vs observed</h2>${table([{ label: "Scenario", html: (r) => `<strong>${r.scenario_code}</strong><br>${esc(r.scenario_name)}` },
    { label: "Expected", key: "expected" }, { label: "Observed", html: (r) => `<span class="small">${esc(r.observed)}</span>` }, { label: "Result", html: (r) => statusPill(r.status) },
    { label: "Duration", num: true, html: (r) => fmtMs(r.duration_ms) }], data.latest)}</div>`;
  view.querySelector("#run").addEventListener("click", async (e) => {
    e.target.disabled = true; e.target.innerHTML = `<span class="spinner"></span> Running 14 scenarios&hellip;`;
    const { data: r } = await api("/api/tests/run", { method: "POST" });
    await renderTests();
    view.querySelector("#run-result").innerHTML = `<div class="notice ${r.passed === r.total ? "ok" : "bad"}" style="margin-bottom:16px">Run #${r.test_run_id}: <strong>${r.passed}/${r.total}</strong> scenarios passed.</div>`;
  });
}

// ------------------------------------------------------------------ AI quality
async function renderQuality() {
  const { data } = await api("/api/quality");
  const s = data.summary;
  view.innerHTML = head("AI Quality", "Measured against the ground truth of every synthetic document. Definitions: docs/AI_QUALITY_FRAMEWORK.md.") + `
  <div class="grid g6">
    ${kpi("Field accuracy", pct(s.field_accuracy_pct), "correct fields / scored fields", true)}
    ${kpi("Completeness", pct(s.completeness_pct), "found when present", true)}
    ${kpi("Manual correction", pct(s.manual_correction_rate_pct), `${s.corrected_fields} fields corrected`, true)}
    ${kpi("Fallback rate", pct(s.fallback_rate_pct), `${s.fallback_runs} runs`, true)}
    ${kpi("Error rate", pct(s.error_rate_pct), `${s.failed_runs} failed runs`, true)}
    ${kpi("Avg confidence", fmtConf(s.avg_confidence), "successful runs", true)}
  </div>
  <div class="grid g3" style="margin-top:16px">
    <div class="card"><h2>Success rate by file type</h2><div class="bars">${data.by_family.map((r) => `<div class="bar-row"><span>${esc(r.file_family)} <span class="muted">(${r.runs})</span></span>${bar(r.success_rate_pct, 100, r.success_rate_pct < 90 ? "warn" : "")}<span>${pct(r.success_rate_pct)}</span></div>`).join("")}</div>
      <p class="small muted">DOCX is pulled down by BUG-01 (Jan-Feb). After the fix: see SQL Q03.</p></div>
    <div class="card"><h2>Accuracy by field</h2><div class="bars">${data.by_field.map((r) => `<div class="bar-row"><span>${esc(FIELD_LABELS[r.field_name])}</span>${bar(r.accuracy_pct, 100, r.accuracy_pct < 90 ? "warn" : "")}<span>${pct(r.accuracy_pct)}</span></div>`).join("")}</div></div>
    <div class="card"><h2>Is confidence a useful signal?</h2>${table([{ label: "Confidence", key: "band" }, { label: "Runs", num: true, key: "runs" },
      { label: "Field accuracy", html: (r) => `<div style="min-width:110px">${bar(r.field_accuracy_pct, 100, r.field_accuracy_pct < 80 ? "bad" : r.field_accuracy_pct < 95 ? "warn" : "")}</div>` },
      { label: "", num: true, html: (r) => pct(r.field_accuracy_pct) }], data.confidence_bands)}
      <p class="small muted">Low-confidence runs are exactly where reviewers correct most: the threshold routes them to review.</p></div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Performance by document type</h2>${table([{ label: "Family", key: "file_family" }, { label: "Format", key: "detected_format" }, { label: "Variant", html: (r) => human(r.sample_variant) },
    { label: "Runs", num: true, key: "runs" }, { label: "Success", num: true, html: (r) => pct(r.success_rate_pct) }, { label: "Accuracy", num: true, html: (r) => pct(r.field_accuracy_pct) },
    { label: "Completeness", num: true, html: (r) => pct(r.completeness_pct) }, { label: "Corrections", num: true, html: (r) => pct(r.manual_correction_rate_pct) },
    { label: "Review rate", num: true, html: (r) => pct(r.human_review_rate_pct) }, { label: "Avg conf.", num: true, html: (r) => fmtConf(r.avg_confidence) },
    { label: "Latency", num: true, html: (r) => fmtMs(r.avg_processing_ms) }], data.by_document_type)}</div>
  <div class="grid g3" style="margin-top:16px">
    <div class="card"><h2>Errors</h2>${table([{ label: "Stage", html: (r) => human(r.error_stage) }, { label: "Code", html: (r) => `<code>${esc(r.error_code)}</code>` }, { label: "Format", key: "detected_format" },
      { label: "Runs", num: true, key: "failed_runs" }, { label: "Recovered", num: true, key: "recovered_by_retry" }], data.errors)}</div>
    <div class="card"><h2>Providers</h2>${table([{ label: "Provider", key: "provider" }, { label: "Runs", num: true, key: "runs" }, { label: "Avg conf.", num: true, html: (r) => fmtConf(r.avg_confidence) }], data.by_provider)}</div>
    <div class="card"><h2>Reviewer feedback</h2>${table([{ label: "Type", html: (r) => human(r.feedback_type) }, { label: "Field", html: (r) => FIELD_LABELS[r.field_name] || r.field_name }, { label: "n", num: true, key: "n" }], data.feedback)}</div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Human review by month</h2>${table([{ label: "Month", key: "review_month" }, { label: "Reviews", num: true, key: "reviews" },
    { label: "With corrections", num: true, html: (r) => `${r.reviews_with_corrections} (${pct(r.reviews_with_corrections_pct)})` }, { label: "Field correction rate", num: true, html: (r) => pct(r.field_correction_rate_pct) },
    { label: "Category changes", num: true, key: "category_changes" }, { label: "Avg review time", num: true, html: (r) => `${r.avg_review_seconds} s` }], data.reviews)}
    <p class="small muted">Reviewers in the dataset are simulated (human_reviews.is_simulated = 1). Reviews made in this demo are recorded as real.</p></div>`;
}

// ------------------------------------------------------------------ audit
async function renderAudit(filter) {
  const type = filter || "";
  const { data } = await api(`/api/audit${type ? `?event_type=${encodeURIComponent(type)}` : ""}`);
  view.innerHTML = head("Audit", "Every step of the workflow leaves a trace. Metadata only: no document text, no extracted content, no free-text questions.") + `
  <div class="notice teal" style="margin-bottom:16px">Logged: document id, format, processing status, latency, provider, error code. <strong>Never logged:</strong> full document content, client secrets, unnecessary personal data. Keys outside an allow-list are dropped; e-mail, phone and IBAN patterns are redacted.</div>
  <div class="card"><div class="chips" style="margin-bottom:12px"><button data-t="" class="${type ? "" : "on"}">All</button>${data.types.map((t) => `<button data-t="${esc(t.event_type)}" class="${t.event_type === type ? "on" : ""}">${esc(t.event_type)} (${t.n})</button>`).join("")}</div>
  ${table([{ label: "#", key: "event_id" }, { label: "Time", html: (r) => shortTime(r.event_time) }, { label: "Event", html: (r) => `<code>${esc(r.event_type)}</code>` },
    { label: "Actor", key: "actor" }, { label: "Entity", html: (r) => (r.entity_type ? `${esc(r.entity_type)} #${esc(r.entity_id)}` : "") }, { label: "Format", key: "format" },
    { label: "Status", key: "processing_status" }, { label: "Provider", key: "provider" }, { label: "Latency", num: true, html: (r) => (r.latency_ms ? fmtMs(r.latency_ms) : "") },
    { label: "Error", html: (r) => (r.error_code ? `<code>${esc(r.error_code)}</code>` : "") }, { label: "Details (allow-listed)", html: (r) => `<span class="small mono">${esc(r.details || "")}</span>` }], data.events)}</div>`;
  view.querySelectorAll("[data-t]").forEach((b) => b.addEventListener("click", () => renderAudit(b.dataset.t)));
}

// ------------------------------------------------------------------ boot
(async function boot() {
  const { data } = await api("/api/meta");
  if (data) {
    META = data;
    document.getElementById("chain").innerHTML = `AI chain: ${data.provider_chain.map(esc).join(" &rarr; ")}${data.bug_replay.length ? `<br><strong style="color:#fbbf24">Bug replay: ${data.bug_replay.map(esc).join(", ")}</strong>` : ""}`;
  }
  window.addEventListener("hashchange", router);
  router();
})();
