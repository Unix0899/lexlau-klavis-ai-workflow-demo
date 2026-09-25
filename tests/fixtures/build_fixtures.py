"""Write the deterministic test fixtures (synthetic) and their expected values.

    python tests/fixtures/build_fixtures.py

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
"""
import json
import random
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
from synthetic_documents import (BANNER, build_text, docx_bytes, image_bytes, make_case,  # noqa: E402
                                 pdf_bytes, render)


def _case(seq, category, **overrides):
    case = make_case(random.Random(seq), seq, category)
    case.update(court_in_text_only=False, date_style="slash", amount_style="eur_prefix")
    case["labels"] = {k: v for k, v in case["labels"].items()}
    case.update(overrides)
    return case


def multiple_dates_doc():
    """Four dates written in four different formats, plus the expected normalised list."""
    lines = [BANNER, "Court summons", "Reference: SYN-26-90006",
             "Matter: Breach of the software maintenance service agreement",
             "Client: Quillfield Systems SRL", "Opposing party: Pellbrook Digital BV",
             "Jurisdiction: Brussels Court of First Instance", "",
             "The service agreement was breached and the termination clause was applied.", "",
             "Date of incident: 2026-01-07", "Date of this letter: 3 February 2026",
             "Response deadline: 24/02/2026", "Hearing date: March 18, 2026",
             "Amount claimed: EUR 18,400.00", "",
             "All names, companies and references in this document are fictional."]
    expected = {
        "case_title": "Breach of the software maintenance service agreement",
        "case_reference": "SYN-26-90006", "client_name": "Quillfield Systems SRL",
        "opposing_party": "Pellbrook Digital BV", "document_type": "Court summons",
        "jurisdiction": "Brussels Court of First Instance",
        "important_dates": [
            {"label": "incident_date", "date": "2026-01-07", "incomplete": False},
            {"label": "notice_date", "date": "2026-02-03", "incomplete": False},
            {"label": "response_deadline", "date": "2026-02-24", "incomplete": False},
            {"label": "hearing_date", "date": "2026-03-18", "incomplete": False}],
        "amounts": [{"label": "amount_claimed", "value": 18400.0}],
        "case_category": "Contract dispute"}
    return docx_bytes(lines), expected


def main():
    rng = random.Random(90000)
    out = {}

    def save(name, content, expected, note):
        (HERE / name).write_bytes(content)
        out[name] = {"note": note, "expected": expected}

    c1 = _case(90001, "Commercial dispute", goods="office furniture",
               title="Unpaid invoices for office furniture")
    b, t, _ = render(c1, "clean", "pdf", rng)
    save("clean_notice.pdf", b, t, "TEST 001 / 014 - clean PDF, all required fields present")

    c2 = _case(90002, "Employment matter")
    b, t, _ = render(c2, "clean", "docx", rng)
    save("clean_letter.docx", b, t, "TEST 002 / 014 - DOCX")

    c3 = _case(90003, "Contract dispute")
    b, t, _ = render(c3, "clean", "png", rng)
    save("clean_scan.png", b, t, "TEST 003 / 014 - clean image (simulated OCR text layer)")

    c4 = _case(90004, "Commercial dispute", goods="IT hardware", title="Late payment for delivered IT hardware")
    b, t, _ = render(c4, "degraded", "jpg", random.Random(4))
    save("degraded_photo.jpg", b, t, "TEST 004 - degraded photo, OCR noise")

    c5 = _case(90005, "Commercial dispute", goods="catering supplies",
               title="Unpaid invoices for catering supplies")
    pages, t = build_text(c5, "clean", rng)
    pages = [[ln for ln in p if not ln.startswith((c5["labels"]["jurisdiction"], c5["labels"]["amount_claimed"]))]
             for p in pages]
    t["jurisdiction"] = None
    t["amounts"] = [a for a in t["amounts"] if a["label"] != "amount_claimed"]
    save("missing_fields.pdf", pdf_bytes(pages), t, "TEST 005 - jurisdiction and amount claimed absent")

    b, t = multiple_dates_doc()
    save("multiple_dates.docx", b, t, "TEST 006 - four dates in four formats")

    c7 = _case(90007, "Contract dispute")
    b, t, _ = render(c7, "multipage", "pdf", rng)
    save("multipage_contract.pdf", b, t, "TEST 014 - three-page PDF, fields spread over pages")

    c8 = _case(90008, "Commercial dispute", goods="cardboard packaging",
               title="Unpaid invoices for cardboard packaging")
    b, t, _ = render(c8, "clean", "pdf", rng)
    save("cardboard_commercial.pdf", b, t, "TEST 014 - category regression ('board' inside 'cardboard')")

    c9 = _case(90009, "Corporate matter")
    for fmt in ("pdf", "docx", "png"):
        b, t, _ = render(c9, "clean", fmt, random.Random(9))
        save(f"mixed_same_case.{fmt}", b, t, "TEST 013 - the same case in three formats")

    c10 = _case(90010, "Contract dispute")
    for variant in ("contradictory",):
        b, t, _ = render(c10, variant, "docx", random.Random(3))
        save("contradictory.docx", b, t, "conflicting values must be flagged for review")

    (HERE / "invalid_file.pdf").write_bytes(bytes(random.Random(11).randrange(256) for _ in range(2048)))
    out["invalid_file.pdf"] = {"note": "TEST 011 - random bytes with a .pdf name", "expected": None}
    (HERE / "renamed_executable.docx").write_bytes(b"MZ\x90\x00" + b"\x00" * 1020)
    out["renamed_executable.docx"] = {"note": "TEST 011 - executable header renamed .docx", "expected": None}

    (HERE / "expected.json").write_text(json.dumps(
        {"generated": date(2026, 9, 24).isoformat(),
         "disclosure": "Synthetic demonstration data. No real client, legal-case or confidential "
                       "LexLau/Klavis data is included.",
         "fixtures": out}, indent=2), encoding="utf-8")
    print(f"{len(out)} fixtures written to {HERE}")


if __name__ == "__main__":
    main()
