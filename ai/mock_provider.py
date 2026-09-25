"""Deterministic local providers (default). No API key, no network.

MockAIProvider ("mock-primary")
    Rule-based extraction: labelled lines, OCR-tolerant label matching, a court
    gazetteer, date / amount normalisation and conflict detection.
MockFallbackProvider ("mock-fallback")
    A deliberately simpler backup engine: strict labels only, lower confidence.
    It is what the chain falls back to when the primary fails.

`simulate_failure` lets tests and the dataset builder inject a provider failure
("PROVIDER_TIMEOUT", "PROVIDER_ERROR", "INVALID_OUTPUT") in a reproducible way.
Mock AI cannot reproduce all behaviours of commercial LLMs; see docs/AI_QUALITY_FRAMEWORK.md.
"""
import re
from datetime import date

from . import bug_replay
from .category_suggestion import suggest_category as _keyword_category
from .ingestion import text_quality
from .provider_interface import AIProvider, ProviderError, ProviderTimeout

LABELS = {
    "case_reference": ["Case reference", "Our reference", "Reference", "File number", "Ref"],
    "case_title": ["Matter", "Subject", "Re"],
    "client_name": ["On behalf of", "Our client", "Client"],
    "opposing_party": ["Opposing party", "Counterparty", "Respondent", "Against"],
    "jurisdiction": ["Jurisdiction", "Competent court", "Court"],
}
DATE_LABELS = {
    "incident_date": ["Date of incident", "Incident date", "Date of the facts"],
    "notice_date": ["Date of this letter", "Notice date", "Letter date"],
    "response_deadline": ["Response deadline", "Deadline for response", "Reply by"],
    "hearing_date": ["Hearing date", "Hearing scheduled"],
}
AMOUNT_LABELS = {
    "amount_claimed": ["Amount claimed", "Claimed amount", "Principal amount"],
    "late_interest": ["Late interest", "Interest"],
    "contractual_penalty": ["Contractual penalty", "Penalty"],
}
DOCUMENT_TYPES = [
    "Formal notice", "Service agreement", "Invoice dispute letter",
    "Employment termination letter", "Shareholder letter", "Administrative decision",
    "Court summons",
]
COURTS = [
    "Brussels Enterprise Court", "Antwerp Enterprise Court", "Ghent Enterprise Court",
    "Brussels Labour Court", "Liege Labour Court", "Ghent Labour Court",
    "Brussels Court of First Instance", "Namur Court of First Instance",
    "Council of State", "Leuven Justice of the Peace",
]
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}

# OCR confusions the tolerant matcher accepts (letter -> character class)
_OCR_CLASS = {"o": "[o0]", "l": "[l1i|]", "i": "[i1l!|]", "e": "[ec]", "s": "[s5]",
              "b": "[b8]", "a": "[ao@]", "t": "[t7]", "g": "[g9]", "c": "[ce]"}
_OCR_DIGITS = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "i": "1", "|": "1",
                             "S": "5", "s": "5", "B": "8", "Z": "2"})

CONF_STRICT, CONF_FUZZY, CONF_GAZETTEER, CONF_HEADING = 0.95, 0.72, 0.68, 0.93


def _fuzzy_body(label):
    return "".join(_OCR_CLASS.get(ch.lower(), re.escape(ch)) if ch != " " else r"\s+"
                   for ch in label)


def _label_regex(label, fuzzy):
    if fuzzy:
        body = _fuzzy_body(label)
        sep = r"\s*[:;.]"
    else:
        body = re.escape(label).replace(r"\ ", r"\s+")
        sep = r"\s*:"
    # optional parenthetical qualifier, e.g. "Amount claimed (revised):"
    return re.compile(r"^\s*" + body + r"\.?(?:\s*\(([^)]*)\))?" + sep + r"\s*(.+?)\s*$", re.I)


def _clean(value):
    value = re.sub(r"\s+", " ", value).strip().rstrip(".;,")
    return value or None


def find_labelled(lines, labels, fuzzy):
    """All (value, qualifier) pairs for any of the labels, in document order."""
    hits = []
    regexes = [_label_regex(lab, fuzzy) for lab in labels]
    for line in lines:
        for rx in regexes:
            m = rx.match(line)
            if m:
                v = _clean(m.group(2))
                if v:
                    hits.append((v, (m.group(1) or "").strip()))
                break
    return hits


# ---------------------------------------------------------------- normalisation
def parse_date(raw):
    """Return (iso_date | None, incomplete: bool). European day-first order."""
    s = raw.strip().rstrip(".")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _iso(int(m[1]), int(m[2]), int(m[3])), False
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
    if m:
        return _iso(int(m[3]), int(m[2]), int(m[1])), False
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m and m[2].lower() in MONTHS:
        return _iso(int(m[3]), MONTHS[m[2].lower()], int(m[1])), False
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", s)
    if m and m[1].lower() in MONTHS:
        return _iso(int(m[3]), MONTHS[m[1].lower()], int(m[2])), False
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", s)
    if m and m[1].lower() in MONTHS:
        return None, True  # month + year only: "date incomplete"
    return None, False


def _iso(y, mo, d):
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_amount(raw):
    """'EUR 12,450.00' / '12.450,00 EUR' / '€ 980' -> (12450.0, 'EUR')."""
    s = raw.replace("€", " EUR ").replace("euros", "EUR").replace("euro", "EUR")
    currency = "EUR" if re.search(r"\bEUR\b", s, re.I) else None
    m = re.search(r"\d[\d .,]*", s)
    if not m:
        return None, currency
    num = m.group(0).strip().replace(" ", "")
    if "," in num and "." in num:
        dec = "," if num.rfind(",") > num.rfind(".") else "."
        num = num.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in num:
        head, _, tail = num.rpartition(",")
        num = num.replace(",", "") if len(tail) == 3 else head.replace(",", "") + "." + tail
    elif "." in num:
        head, _, tail = num.rpartition(".")
        num = num.replace(".", "") if len(tail) == 3 else head.replace(".", "") + "." + tail
    try:
        return round(float(num), 2), currency
    except ValueError:
        return None, currency


class MockAIProvider(AIProvider):
    name = "mock-primary"
    fuzzy_labels = True
    use_gazetteer = True
    confidence_cap = 1.0

    # ------------------------------------------------------------ failure injection
    def _maybe_fail(self, simulate_failure):
        if not simulate_failure:
            return None
        if simulate_failure == "PROVIDER_TIMEOUT":
            raise ProviderTimeout(f"{self.name} did not answer within the timeout")
        if simulate_failure == "PROVIDER_ERROR":
            raise ProviderError(f"{self.name} returned a server error")
        if simulate_failure == "INVALID_OUTPUT":
            return {"fields": "malformed"}  # breaks the contract on purpose
        raise ValueError(f"Unknown simulated failure {simulate_failure}")

    # ------------------------------------------------------------------ extraction
    def extract(self, text, simulate_failure=None):
        broken = self._maybe_fail(simulate_failure)
        if broken is not None:
            return broken
        lines = [ln for ln in text.splitlines() if ln.strip()]
        quality = text_quality(text)
        q_factor = 0.85 + 0.15 * quality
        fields, conflicts = {}, []

        for name, labels in LABELS.items():
            value, conf, method, hits = self._text_field(lines, labels)
            if name == "jurisdiction" and value is None and self.use_gazetteer:
                value, conf, method = self._gazetteer(text)
            if name == "case_reference" and value:
                value = self._normalise_reference(value)
            distinct = list(dict.fromkeys(h[0] for h in hits))
            if len(distinct) > 1:
                conflicts.append({"field": name, "values": distinct})
                conf *= 0.6
            fields[name] = self._f(value, conf * q_factor, method)

        doc_type, conf, method = self._document_type(lines)
        fields["document_type"] = self._f(doc_type, conf * q_factor, method)

        dates, dconf, dconflicts = self._dates(lines)
        fields["important_dates"] = self._f(dates, dconf * q_factor, "label" if dates else None)
        conflicts += dconflicts

        amounts, aconf, aconflicts = self._amounts(lines)
        fields["amounts"] = self._f(amounts, aconf * q_factor, "label" if amounts else None)
        conflicts += aconflicts
        return {"fields": fields, "conflicts": conflicts, "text_quality": quality}

    def _f(self, value, conf, method):
        empty = value is None or value == []
        return {"value": value, "confidence": 0.0 if empty else round(min(conf, self.confidence_cap), 3),
                "method": None if empty else method}

    def _text_field(self, lines, labels):
        hits = find_labelled(lines, labels, fuzzy=False)
        if hits:
            return hits[0][0], CONF_STRICT, "label", hits
        if self.fuzzy_labels:
            hits = find_labelled(lines, labels, fuzzy=True)
            if hits:
                return hits[0][0], CONF_FUZZY, "ocr_tolerant_label", hits
        return None, 0.0, None, []

    @staticmethod
    def _normalise_reference(value):
        m = re.search(r"([S5][Y][N])\s*[-‐]\s*([0-9OoIl|]{2})\s*[-‐]\s*([0-9OoIlS|]{5})", value)
        if not m:
            return value
        return f"SYN-{m[2].translate(_OCR_DIGITS)}-{m[3].translate(_OCR_DIGITS)}"

    def _gazetteer(self, text):
        low = text.lower()
        for court in COURTS:
            if court.lower() in low:
                return court, CONF_GAZETTEER, "gazetteer"
        return None, 0.0, None

    def _document_type(self, lines):
        for line in lines[:8]:
            clean = line.strip().lower()
            for dt in DOCUMENT_TYPES:
                if clean == dt.lower():
                    return dt, CONF_HEADING, "heading"
        if self.fuzzy_labels:
            for line in lines[:8]:
                for dt in DOCUMENT_TYPES:
                    if re.fullmatch(_fuzzy_body(dt), line.strip(), re.I):
                        return dt, CONF_FUZZY, "ocr_tolerant_heading"
        return None, 0.0, None

    def _dates(self, lines):
        out, confs, conflicts = [], [], []
        for label, labels in DATE_LABELS.items():
            hits = find_labelled(lines, labels, fuzzy=False)
            conf = CONF_STRICT
            if not hits and self.fuzzy_labels:
                hits, conf = find_labelled(lines, labels, fuzzy=True), CONF_FUZZY
            if not hits:
                continue
            parsed = []
            for raw, _q in hits:
                iso, incomplete = parse_date(raw)
                c = conf
                if iso is None and not incomplete and self.fuzzy_labels:
                    iso, incomplete = parse_date(raw.translate(_OCR_DIGITS))
                    c = min(conf, CONF_FUZZY)
                parsed.append((iso, incomplete, raw, c))
            iso, incomplete, raw, c = parsed[0]
            if incomplete:
                c = 0.5
            elif iso is None:
                c = 0.3
            distinct = list(dict.fromkeys(p[0] or p[2] for p in parsed))
            if len(distinct) > 1:
                conflicts.append({"field": "important_dates", "label": label, "values": distinct})
                c *= 0.6
            out.append({"label": label, "date": iso, "raw": raw, "incomplete": incomplete})
            confs.append(c)
        return out, (min(confs) if confs else 0.0), conflicts

    def _amounts(self, lines):
        out, confs, conflicts = [], [], []
        for label, labels in AMOUNT_LABELS.items():
            hits = find_labelled(lines, labels, fuzzy=False)
            conf = CONF_STRICT
            if not hits and self.fuzzy_labels:
                hits, conf = find_labelled(lines, labels, fuzzy=True), CONF_FUZZY
            if not hits:
                continue
            parsed = []
            for raw, _q in hits:
                value, currency = parse_amount(raw)
                c = conf
                if value is None and self.fuzzy_labels:
                    value, currency = parse_amount(raw.translate(_OCR_DIGITS))
                    c = min(conf, CONF_FUZZY)
                parsed.append((value, currency, raw, c))
            value, currency, raw, c = parsed[0]
            if value is None:
                c = 0.3
            distinct = list(dict.fromkeys(p[0] if p[0] is not None else p[2] for p in parsed))
            if len(distinct) > 1:
                conflicts.append({"field": "amounts", "label": label, "values": distinct})
                c *= 0.6
            out.append({"label": label, "value": value, "currency": currency or "EUR", "raw": raw})
            confs.append(c)
        if bug_replay.is_on("missing_as_zero") and not any(a["label"] == "amount_claimed" for a in out):
            # BUG-05 replay: an absent amount is returned as 0.00, so it is never reported missing
            out.insert(0, {"label": "amount_claimed", "value": 0.0, "currency": "EUR", "raw": ""})
            confs.append(CONF_STRICT)
        return out, (min(confs) if confs else 0.0), conflicts

    # ------------------------------------------------------------------- category
    def suggest_category(self, text, simulate_failure=None):
        broken = self._maybe_fail(simulate_failure)
        if broken is not None:
            return {"category": "Not a category", "confidence": 2}
        out = _keyword_category(text)
        out["confidence"] = min(out["confidence"], self.confidence_cap)
        return out

    # ------------------------------------------------------------------- summary
    def summarise(self, case, simulate_failure=None):
        self._maybe_fail(simulate_failure)
        title = case.get("case_title") or "Untitled matter"
        parts = [f"{title}."]
        client, opp = case.get("client_name"), case.get("opposing_party")
        if client and opp:
            parts.append(f"{client} is the client; the opposing party is {opp}.")
        elif client:
            parts.append(f"{client} is the client; the opposing party is not identified yet.")
        if case.get("case_category"):
            parts.append(f"Suggested category: {case['case_category']}.")
        if case.get("jurisdiction"):
            parts.append(f"Jurisdiction: {case['jurisdiction']}.")
        dates = [d for d in case.get("important_dates") or [] if d.get("date")]
        if dates:
            parts.append("Key dates: " + ", ".join(
                f"{d['label'].replace('_', ' ')} {d['date']}" for d in dates) + ".")
        amounts = [a for a in case.get("amounts") or [] if a.get("value") is not None]
        if amounts:
            parts.append("Amounts: " + ", ".join(
                f"{a['label'].replace('_', ' ')} {a.get('currency') or 'EUR'} {a['value']:,.2f}"
                for a in amounts) + ".")
        missing = case.get("missing_fields") or []
        if missing:
            parts.append("Still missing: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
        return " ".join(parts)

    # ------------------------------------------------------------------ assistant
    def answer(self, question, case, simulate_failure=None):
        self._maybe_fail(simulate_failure)
        q = question.lower()
        if re.search(r"\b(should i|advice|advise|will (i|we) win|chances|recommend|sue)\b", q):
            return ("I can't give legal advice. I can only describe the structured information "
                    "extracted from this synthetic case.")
        if re.search(r"part(y|ies)|client|opposing|who", q):
            return (f"Client: {case.get('client_name') or 'not identified'}. "
                    f"Opposing party: {case.get('opposing_party') or 'not identified'}.")
        if re.search(r"date|deadline|when|hearing", q):
            dates = case.get("important_dates") or []
            if not dates:
                return "No dates were detected in this case."
            return "Detected dates: " + "; ".join(
                f"{d['label'].replace('_', ' ')}: {d.get('date') or (d.get('raw') or '?') + ' (incomplete)'}"
                for d in dates) + "."
        if re.search(r"missing|incomplete|lack", q):
            missing = case.get("missing_fields") or []
            return ("Missing information: " + ", ".join(m.replace("_", " ") for m in missing) + "."
                    if missing else "No required field is missing.")
        if re.search(r"amount|how much|eur|money|claim", q):
            amounts = case.get("amounts") or []
            if not amounts:
                return "No amount was detected."
            return "Amounts: " + "; ".join(
                f"{a['label'].replace('_', ' ')}: {a.get('currency') or 'EUR'} "
                + (f"{a['value']:,.2f}" if a.get("value") is not None else "unreadable")
                for a in amounts) + "."
        if re.search(r"summar|overview|about", q):
            return self.summarise(case)
        if re.search(r"categor|type of case|kind of case", q):
            return f"Category: {case.get('case_category') or 'not set'}."
        if re.search(r"court|jurisdiction", q):
            return f"Jurisdiction: {case.get('jurisdiction') or 'not identified'}."
        return ("I can answer questions about the parties, dates, amounts, category, jurisdiction, "
                "missing information, or summarise this synthetic case.")


class MockFallbackProvider(MockAIProvider):
    """Simpler backup engine: strict labels only, no gazetteer, confidence capped."""

    name = "mock-fallback"
    fuzzy_labels = False
    use_gazetteer = False
    confidence_cap = 0.85
