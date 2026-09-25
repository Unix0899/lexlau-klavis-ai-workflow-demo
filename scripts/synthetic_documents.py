"""Synthetic legal documents: fictional content + PDF / DOCX / PNG / JPG writers.

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
Every person, company, municipality, reference and amount below is invented. The
court names are generic public institution names used only as labels.

No third-party document library is needed: the PDF and DOCX files are written by
hand (minimal valid structures); images use Pillow.
"""
import io
import random
import zipfile
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

BANNER = "SYNTHETIC DEMONSTRATION DOCUMENT - FICTIONAL DATA - NOT A REAL CASE"

COMPANY_A = ["Brightwater", "Norvale", "Quillfield", "Ambermoor", "Kestrelpoint", "Silverbirch",
             "Oakhaven", "Lindenbrook", "Redcliff", "Harbourline", "Veldon", "Castellan", "Greywood",
             "Tamsinworth", "Brookhollow", "Aldenmere", "Fernhill", "Wexmoor", "Duskwater", "Merriton",
             "Calloway Vale", "Orrinford", "Pellbrook", "Thornlea"]
COMPANY_B = ["Interiors", "Logistics", "Consulting", "Foods", "Digital", "Construction", "Retail",
             "Facilities", "Print", "Mobility", "Packaging", "Systems", "Catering", "Studios"]
LEGAL_FORMS = ["SRL", "BV", "SA", "NV"]
FIRST = ["Elise", "Tomas", "Noor", "Maxime", "Ines", "Jonas", "Lotte", "Amir", "Clara", "Victor",
         "Mila", "Ruben", "Sanne", "Yannick", "Leila", "Bram", "Oona", "Dario", "Femke", "Joris"]
LAST = ["Vandermolen", "Dufrasne", "Kellwyn", "Moreau-Lint", "Ostaven", "Brecquet", "Halvorn",
        "Delacroixe", "Verbrugh", "Talmont", "Quenneville", "Arlenbos", "Stroobaert", "Wyndael",
        "Pellegrand", "Rondeaux", "Vissenaeken", "Maerlant-Oost"]
MUNICIPALITIES = ["Municipality of Aldenmere", "Municipality of Westrook", "Municipality of Orrinford",
                  "Regional Environment Agency (fictional)", "Municipality of Thornlea"]

COURTS = {
    "Commercial dispute": ["Brussels Enterprise Court", "Antwerp Enterprise Court", "Ghent Enterprise Court",
                           "Leuven Justice of the Peace"],
    "Contract dispute": ["Brussels Court of First Instance", "Namur Court of First Instance",
                         "Antwerp Enterprise Court"],
    "Employment matter": ["Brussels Labour Court", "Liege Labour Court", "Ghent Labour Court"],
    "Corporate matter": ["Brussels Enterprise Court", "Ghent Enterprise Court"],
    "Administrative matter": ["Council of State", "Namur Court of First Instance"],
    "Other": ["Brussels Court of First Instance", "Leuven Justice of the Peace"],
}
DOC_TYPES = {
    "Commercial dispute": ["Formal notice", "Invoice dispute letter"],
    "Contract dispute": ["Formal notice", "Court summons"],
    "Employment matter": ["Employment termination letter", "Formal notice"],
    "Corporate matter": ["Shareholder letter", "Court summons"],
    "Administrative matter": ["Administrative decision", "Formal notice"],
    "Other": ["Formal notice"],
}
GOODS = ["office furniture", "catering supplies", "IT hardware", "cardboard packaging", "printed brochures"]
SERVICES = ["cleaning", "software maintenance", "facility management", "marketing"]

LABEL_CHOICES = {
    "case_reference": ["Reference", "Our reference", "File number"],
    "case_title": ["Matter", "Subject"],
    "client_name": ["Client", "On behalf of"],
    "opposing_party": ["Opposing party", "Counterparty", "Respondent"],
    "jurisdiction": ["Jurisdiction", "Competent court"],
    "incident_date": ["Date of incident", "Incident date", "Date of the facts"],
    "notice_date": ["Date of this letter", "Notice date"],
    "response_deadline": ["Response deadline", "Reply by"],
    "hearing_date": ["Hearing date"],
    "amount_claimed": ["Amount claimed", "Principal amount"],
    "late_interest": ["Late interest"],
    "contractual_penalty": ["Contractual penalty"],
}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]


# ------------------------------------------------------------------ fictional case facts
def company(rng):
    return f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)} {rng.choice(LEGAL_FORMS)}"


def person(rng):
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def make_case(rng, seq, category=None):
    category = category or rng.choices(
        ["Commercial dispute", "Contract dispute", "Employment matter", "Corporate matter",
         "Administrative matter", "Other"], weights=[30, 22, 20, 12, 12, 4])[0]
    reference = f"SYN-26-{seq:05d}"
    goods = rng.choice(GOODS)
    svc = rng.choice(SERVICES)
    if category == "Commercial dispute":
        client, opposing = company(rng), company(rng)
        title = rng.choice([f"Unpaid invoices for {goods}", f"Late payment for delivered {goods}",
                            f"Disputed delivery of {goods}"])
        amount = rng.randrange(1_200, 60_000) + rng.choice([0, 0.5, 0.25, 0.8])
    elif category == "Contract dispute":
        client, opposing = company(rng), company(rng)
        title = rng.choice([f"Breach of the {svc} service agreement", f"Early termination of the {svc} contract",
                            f"Non-performance under the {svc} agreement"])
        amount = rng.randrange(4_000, 95_000)
    elif category == "Employment matter":
        client, opposing = person(rng), company(rng)
        title = rng.choice(["Contested dismissal of an employee", "Unpaid overtime claim",
                            "Notice period dispute"])
        amount = rng.randrange(2_500, 38_000) + rng.choice([0, 0.4])
    elif category == "Corporate matter":
        client, opposing = company(rng), person(rng)
        title = rng.choice(["Shareholder dispute over a share transfer", "Contested board resolution",
                            "Challenge to a capital increase"])
        amount = rng.randrange(10_000, 90_000)
    elif category == "Administrative matter":
        client, opposing = company(rng), rng.choice(MUNICIPALITIES)
        title = rng.choice(["Appeal against a permit refusal", "Contested municipal fine",
                            "Appeal against a zoning decision"])
        amount = rng.randrange(500, 15_000)
    else:
        client, opposing = person(rng), person(rng)
        title = "Request for a copy of a mediation record"
        amount = rng.randrange(150, 900)
    while opposing == client:
        opposing = company(rng)

    incident = date(2025, 9, 1) + timedelta(days=rng.randrange(0, 240))
    notice = incident + timedelta(days=rng.randrange(10, 60))
    deadline = notice + timedelta(days=rng.choice([15, 21, 30]))
    dates = [("incident_date", incident), ("notice_date", notice), ("response_deadline", deadline)]
    if rng.random() < 0.3:
        dates.append(("hearing_date", deadline + timedelta(days=rng.randrange(30, 90))))
    amounts = [("amount_claimed", round(amount, 2))]
    if rng.random() < 0.5 and category != "Other":
        amounts.append(("late_interest", round(amount * rng.uniform(0.02, 0.08), 2)))
    if category == "Contract dispute" and rng.random() < 0.5:
        amounts.append(("contractual_penalty", round(amount * 0.1, 2)))

    return {
        "category": category, "reference": reference, "title": title, "client": client,
        "opposing": opposing, "jurisdiction": rng.choice(COURTS[category]),
        "document_type": rng.choice(DOC_TYPES[category]), "dates": dates, "amounts": amounts,
        "goods": goods, "service": svc,
        "labels": {k: rng.choice(v) for k, v in LABEL_CHOICES.items()},
        "date_style": rng.choice(["iso", "slash", "dot", "long", "us_long"]),
        "amount_style": rng.choice(["eur_prefix", "euro_suffix", "symbol", "plain_euros"]),
        "court_in_text_only": rng.random() < 0.1,
    }


def fmt_date(d, style):
    return {"iso": d.isoformat(), "slash": d.strftime("%d/%m/%Y"), "dot": d.strftime("%d.%m.%Y"),
            "long": f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}",
            "us_long": f"{MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"}[style]


def fmt_amount(v, style):
    whole, cents = f"{v:,.2f}".split(".")
    if style == "eur_prefix":
        return f"EUR {whole}.{cents}"
    eu = whole.replace(",", ".") + "," + cents
    if style == "euro_suffix":
        return f"{eu} EUR"
    if style == "symbol":
        return f"€ {eu}"
    return f"{whole.replace(',', ' ')},{cents} euros"


def narrative(case, rng):
    c, o = case["client"], case["opposing"]
    cat = case["category"]
    if cat == "Commercial dispute":
        g = case["goods"]
        if "cardboard" in g:
            return [f"Our client supplied cardboard, cardboard sleeves and cardboard trays to {o}.",
                    "The cardboard was accepted on receipt and stored in cardboard crates; "
                    "the cardboard specification was met.",
                    f"{o} has not paid the related invoices."]
        return [f"Our client delivered {g} to {o} under several purchase orders.",
                "The invoices remain unpaid despite two payment reminders.",
                "The customer has not raised any complaint about the goods within the agreed period."]
    if cat == "Contract dispute":
        return [f"{c} and {o} signed a {case['service']} service agreement.",
                "Our client considers that the termination clause was applied without the required notice, "
                "which amounts to a breach of contract.",
                "The contractual penalty clause is invoked for non-performance."]
    if cat == "Employment matter":
        return [f"Our client was an employee of {o} and contests the dismissal.",
                "The employer did not respect the notice period and several overtime hours remain unpaid.",
                "The salary slips of the last six months are attached."]
    if cat == "Corporate matter":
        return [f"Our client is a shareholder of a company in which {o} is a director.",
                "The board adopted a resolution on a share transfer without convening the general meeting.",
                "The articles of association require the approval of the shareholders."]
    if cat == "Administrative matter":
        return [f"{o} issued an administrative decision concerning our client.",
                "The permit application was refused and a fine was imposed by the public authority.",
                "Our client contests the zoning grounds relied upon."]
    return ["Our client requests a copy of the record of a mediation session held earlier this year.",
            "No claim is raised at this stage."]


# ------------------------------------------------------------------ document text per variant
def build_text(case, variant, rng):
    """Return (pages: list[list[str]], ground_truth: dict) for one document."""
    lab = case["labels"]
    ds, ams = case["date_style"], case["amount_style"]
    truth_dates = [{"label": k, "date": d.isoformat(), "incomplete": False} for k, d in case["dates"]]
    truth_amounts = [{"label": k, "value": v} for k, v in case["amounts"]]
    truth = {"case_title": case["title"], "case_reference": case["reference"],
             "client_name": case["client"], "opposing_party": case["opposing"],
             "document_type": case["document_type"], "jurisdiction": case["jurisdiction"],
             "important_dates": truth_dates, "amounts": truth_amounts, "case_category": case["category"]}

    header = [BANNER, case["document_type"], f"{lab['case_reference']}: {case['reference']}",
              f"{lab['case_title']}: {case['title']}", f"{lab['client_name']}: {case['client']}"]
    parties = [f"{lab['opposing_party']}: {case['opposing']}"]
    court = [] if case["court_in_text_only"] else [f"{lab['jurisdiction']}: {case['jurisdiction']}"]
    body = narrative(case, rng)
    if case["court_in_text_only"]:
        body.append(f"The matter may be brought before the {case['jurisdiction']}.")
    date_lines = [f"{lab[k]}: {fmt_date(d, ds)}" for k, d in case["dates"]]
    amount_lines = [f"{lab[k]}: {fmt_amount(v, ams)}" for k, v in case["amounts"]]
    footer = ["All names, companies and references in this document are fictional.",
              "Prepared for the Klavis AI Workflow Demo (synthetic portfolio reconstruction)."]

    if variant == "missing_fields":
        removable = ["opposing_party", "jurisdiction", "amount_claimed", "response_deadline"]
        for item in rng.sample(removable, rng.choice([1, 2])):
            if item == "opposing_party":
                parties, truth["opposing_party"] = [], None
            elif item == "jurisdiction":
                court, truth["jurisdiction"] = [], None
                body = [b for b in body if "brought before" not in b]
            elif item == "amount_claimed":
                amount_lines = [a for a in amount_lines if not a.startswith(lab["amount_claimed"])]
                truth["amounts"] = [a for a in truth_amounts if a["label"] != "amount_claimed"]
            else:  # date incomplete: only month and year are given
                d = dict(case["dates"])["response_deadline"]
                date_lines = [f"{lab['response_deadline']}: {MONTH_NAMES[d.month - 1]} {d.year}"
                              if x.startswith(lab["response_deadline"]) else x for x in date_lines]
                truth["important_dates"] = [
                    {"label": "response_deadline", "date": None, "incomplete": True}
                    if t["label"] == "response_deadline" else t for t in truth_dates]

    if variant == "contradictory":
        kind = rng.choice(["amount", "jurisdiction", "date"])
        if kind == "amount" or case["court_in_text_only"]:
            revised = round(case["amounts"][0][1] * rng.choice([1.08, 1.15, 0.9]), 2)
            amount_lines.append(f"{lab['amount_claimed']} (revised, supersedes the amount above): "
                                f"{fmt_amount(revised, ams)}")
            truth["amounts"] = [{"label": a["label"], "value": revised if a["label"] == "amount_claimed"
                                 else a["value"]} for a in truth_amounts]
        elif kind == "jurisdiction":
            other = rng.choice([c for cs in COURTS.values() for c in cs if c != case["jurisdiction"]])
            body.append(f"{lab['jurisdiction']} (per clause 14 of the agreement): {other}")
            truth["jurisdiction"] = other
        else:
            d = dict(case["dates"])["response_deadline"] + timedelta(days=7)
            date_lines.append(f"{lab['response_deadline']} (extended): {fmt_date(d, ds)}")
            truth["important_dates"] = [
                {"label": "response_deadline", "date": d.isoformat(), "incomplete": False}
                if t["label"] == "response_deadline" else t for t in truth_dates]

    if variant == "multipage":
        pages = [header + ["", "Page 1 of 3"],
                 parties + court + [""] + body + ["", "Page 2 of 3"],
                 date_lines + amount_lines + [""] + footer + ["", "Page 3 of 3"]]
    else:
        pages = [header + parties + court + [""] + body + [""] + date_lines + amount_lines + [""] + footer]
    return pages, truth


OCR_SUBS = {"o": "0", "O": "0", "l": "1", "I": "1", "i": "l", "e": "c", "s": "5", "S": "5",
            "a": "o", "B": "8", ":": ";"}


def degrade(pages, rate, rng):
    """Simulate a poor scan / photo: OCR character confusions and a few dropped characters."""
    out = []
    for page in pages:
        new = []
        for line in page:
            if line == BANNER:
                new.append(line)
                continue
            chars = []
            for ch in line:
                r = rng.random()
                if r < rate and ch in OCR_SUBS:
                    chars.append(OCR_SUBS[ch])
                elif r < rate + rate / 6 and ch.isalpha():
                    continue
                else:
                    chars.append(ch)
            new.append("".join(chars))
        out.append(new)
    return out


# ------------------------------------------------------------------ writers
def _pdf_escape(s):
    s = s.replace("€", "EUR")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace")


def pdf_bytes(pages):
    """Minimal valid PDF (Helvetica, one text block per page)."""
    objects = []
    n_pages = len(pages)
    page_ids = [3 + 2 * i for i in range(n_pages)]
    font_id = 3 + 2 * n_pages
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(("<< /Type /Pages /Kids [" + " ".join(f"{p} 0 R" for p in page_ids)
                    + f"] /Count {n_pages} >>").encode())
    for i, lines in enumerate(pages):
        stream = b"BT /F1 10 Tf 56 790 Td 15 TL\n"
        for j, line in enumerate(lines):
            size = b"13" if j == 1 else b"10"
            stream += b"/F1 " + size + b" Tf (" + _pdf_escape(line) + b") Tj T*\n"
        stream += b"ET"
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>").encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def docx_bytes(lines):
    paras = []
    for i, line in enumerate(lines):
        bold = "<w:rPr><w:b/><w:sz w:val=\"28\"/></w:rPr>" if i == 1 else ""
        paras.append(f"<w:p><w:r>{bold}<w:t xml:space=\"preserve\">{_xml_escape(line)}</w:t></w:r></w:p>")
    document = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
                "<w:body>" + "".join(paras) + "</w:body></w:document>")
    content_types = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                     "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                     "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
                     "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                     "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
                     "</Types>")
    rels = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
            "</Relationships>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def image_bytes(lines, ocr_text, fmt, degraded, rng):
    """Render the document as an image and embed the simulated-OCR text layer."""
    w, h = 820, 1160
    img = Image.new("L", (w, h), 245 if degraded else 255)
    draw = ImageDraw.Draw(img)
    body, head = _font(17), _font(24)
    y = 50
    for i, line in enumerate(lines):
        font = head if i == 1 else body
        draw.text((48, y), line.replace("€", "EUR"), fill=30 if not degraded else 70, font=font)
        y += 34 if i == 1 else 26
        if y > h - 40:
            break
    if degraded:
        img = img.rotate(rng.uniform(-2.2, 2.2), fillcolor=235, resample=Image.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(1.1))
        px = img.load()
        for _ in range(2500):
            x, yy = rng.randrange(w), rng.randrange(h)
            px[x, yy] = rng.choice([90, 140, 200])
    buf = io.BytesIO()
    if fmt == "png":
        info = PngInfo()
        info.add_itxt("synthetic_ocr_text", ocr_text)
        img.save(buf, "PNG", pnginfo=info, optimize=True)
    else:
        img.save(buf, "JPEG", quality=55 if degraded else 75, comment=ocr_text.encode("utf-8"))
    return buf.getvalue()


def render(case, variant, fmt, rng):
    """Return (bytes, ground_truth, page_count)."""
    pages, truth = build_text(case, variant, rng)
    printed = [ln for p in pages for ln in p]          # what is on the paper
    if variant == "degraded":
        pages = degrade(pages, 0.018 if fmt == "pdf" else 0.03, rng)
    flat = [ln for p in pages for ln in p]             # what the text layer / OCR returns
    if fmt == "pdf":
        return pdf_bytes(pages), truth, len(pages)
    if fmt == "docx":
        return docx_bytes(flat), truth, 1
    return image_bytes(printed, "\n".join(flat), fmt, variant == "degraded", rng), truth, 1
