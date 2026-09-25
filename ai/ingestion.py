"""Document ingestion: validate the upload, detect the real format, extract text.

Formats are detected from the file content (magic bytes), not from the file name.
Text extraction:
    PDF   -> pypdf text layer
    DOCX  -> word/document.xml read with zipfile (no external dependency)
    Image -> simulated OCR: the synthetic images carry the text an OCR engine would
             have produced (PNG text chunk / JPEG comment). Real OCR is not bundled;
             see docs/ARCHITECTURE.md ("Simulated OCR").
"""
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from . import bug_replay
from .config import MAX_UPLOAD_BYTES

logging.getLogger("pypdf").setLevel(logging.ERROR)  # parser warnings would echo file details

OCR_TEXT_KEY = "synthetic_ocr_text"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class IngestionError(Exception):
    """Controlled rejection. `code` is logged, `message` is shown to the user."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class IngestedDocument:
    format: str
    text: str
    pages: int
    byte_size: int
    sha256: str
    warnings: list = field(default_factory=list)


def detect_format(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
    return None


# --- BUG-01 replay: the historical routing table keyed on the file extension -----------
_LEGACY_EXTENSION_ROUTES = {".pdf": "pdf", ".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".doc": "docx"}


def _legacy_route(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    # ".docx" is missing from the table, so it falls through to the default parser (PDF)
    return _LEGACY_EXTENSION_ROUTES.get(ext, "pdf")


def extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def ingest(content: bytes, filename: str) -> IngestedDocument:
    size = len(content)
    if size == 0:
        raise IngestionError("EMPTY_FILE", "The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise IngestionError(
            "FILE_TOO_LARGE",
            f"File is {size / 1_048_576:.1f} MB; the limit is {MAX_UPLOAD_BYTES / 1_048_576:.0f} MB.")

    detected = detect_format(content)
    if detected is None:
        raise IngestionError("UNSUPPORTED_FORMAT",
                             "Unsupported or unrecognised file. Accepted: PDF, DOCX, PNG, JPG.")

    warnings = []
    ext = extension_of(filename)
    if ext and {"jpeg": "jpg"}.get(ext, ext) != detected:
        warnings.append(f"extension .{ext} does not match detected format {detected}")

    route = _legacy_route(filename) if bug_replay.is_on("docx_routing") else detected
    parser = {"pdf": _pdf_text, "docx": _docx_text, "png": _image_text, "jpg": _image_text}[route]
    try:
        text, pages = parser(content)
    except IngestionError:
        raise
    except Exception as exc:  # parser failure is a controlled error, never a crash
        raise IngestionError("PARSE_ERROR", f"The {route.upper()} parser could not read this file "
                                            f"({type(exc).__name__}).") from None
    text = text.strip()
    if not text:
        raise IngestionError("NO_TEXT_FOUND", "No text could be extracted from this document.")
    return IngestedDocument(detected, text, pages, size, hashlib.sha256(content).hexdigest(), warnings)


def _pdf_text(content):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n".join(pages), len(pages)


def _docx_text(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    for para in root.iter(W_NS + "p"):
        lines.append("".join(t.text or "" for t in para.iter(W_NS + "t")))
    return "\n".join(lines), 1


def _image_text(content):
    from PIL import Image
    with Image.open(io.BytesIO(content)) as img:
        img.load()
        raw = img.info.get(OCR_TEXT_KEY) or img.info.get("comment") or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw.strip():
        raise IngestionError(
            "NO_TEXT_FOUND",
            "Simulated OCR: this demo reads the synthetic text layer embedded in its generated "
            "images. A real OCR engine is not bundled.")
    return raw, 1


def text_quality(text: str) -> float:
    """Share of word tokens that look clean (no letter/digit mix such as 'Cl1ent').

    Used as a proxy for OCR / scan quality; 1.0 = clean text.
    """
    words = re.findall(r"[A-Za-z0-9]{3,}", text)
    if not words:
        return 0.0
    noisy = sum(1 for w in words if re.search(r"[A-Za-z]", w) and re.search(r"\d", w)
                and not re.fullmatch(r"(SYN|[A-Z]{2,})\d+|\d+[A-Za-z]{1,2}", w))
    return round(1 - noisy / len(words), 3)
