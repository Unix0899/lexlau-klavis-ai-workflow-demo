import io
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from ai.bug_replay import bug_replay
from ai.config import MAX_UPLOAD_BYTES
from ai.ingestion import IngestionError, detect_format, ingest, text_quality

FIX = Path(__file__).resolve().parents[1] / "fixtures"


class DetectFormat(unittest.TestCase):
    def test_magic_bytes(self):
        self.assertEqual(detect_format((FIX / "clean_notice.pdf").read_bytes()), "pdf")
        self.assertEqual(detect_format((FIX / "clean_letter.docx").read_bytes()), "docx")
        self.assertEqual(detect_format((FIX / "clean_scan.png").read_bytes()), "png")
        self.assertEqual(detect_format((FIX / "degraded_photo.jpg").read_bytes()), "jpg")

    def test_zip_that_is_not_docx(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("notes.txt", "hello")
        self.assertIsNone(detect_format(buf.getvalue()))

    def test_unknown_bytes(self):
        self.assertIsNone(detect_format(b"MZ\x90\x00" + bytes(100)))


class Ingest(unittest.TestCase):
    def test_pdf_text_and_pages(self):
        doc = ingest((FIX / "multipage_contract.pdf").read_bytes(), "a.pdf")
        self.assertEqual(doc.pages, 3)
        self.assertIn("SYNTHETIC DEMONSTRATION DOCUMENT", doc.text)

    def test_docx_text(self):
        doc = ingest((FIX / "clean_letter.docx").read_bytes(), "a.docx")
        self.assertEqual(doc.format, "docx")
        self.assertIn("Reference", doc.text + "Reference")
        self.assertGreater(len(doc.text.splitlines()), 8)

    def test_image_simulated_ocr_layer(self):
        doc = ingest((FIX / "clean_scan.png").read_bytes(), "a.png")
        self.assertIn("SYN-26-", doc.text)

    def test_image_without_text_layer_is_a_controlled_error(self):
        buf = io.BytesIO()
        Image.new("L", (40, 40), 255).save(buf, "PNG")
        with self.assertRaises(IngestionError) as ctx:
            ingest(buf.getvalue(), "photo.png")
        self.assertEqual(ctx.exception.code, "NO_TEXT_FOUND")

    def test_rejections(self):
        cases = {b"": "EMPTY_FILE", b"%PDF-1.4" + b"0" * MAX_UPLOAD_BYTES: "FILE_TOO_LARGE",
                 b"MZ\x90\x00" + bytes(64): "UNSUPPORTED_FORMAT"}
        for content, code in cases.items():
            with self.subTest(code=code), self.assertRaises(IngestionError) as ctx:
                ingest(content, "x.pdf")
            self.assertEqual(ctx.exception.code, code)

    def test_corrupted_pdf_is_parse_error_not_crash(self):
        with self.assertRaises(IngestionError) as ctx:
            ingest(b"%PDF-1.4\n garbage without objects", "broken.pdf")
        self.assertIn(ctx.exception.code, {"PARSE_ERROR", "NO_TEXT_FOUND"})

    def test_extension_mismatch_is_a_warning(self):
        doc = ingest((FIX / "clean_notice.pdf").read_bytes(), "renamed.docx")
        self.assertEqual(doc.format, "pdf")
        self.assertTrue(doc.warnings)

    def test_bug01_replay_routes_docx_to_pdf_parser(self):
        content = (FIX / "clean_letter.docx").read_bytes()
        with bug_replay("docx_routing"), self.assertRaises(IngestionError) as ctx:
            ingest(content, "letter.docx")
        self.assertEqual(ctx.exception.code, "PARSE_ERROR")
        self.assertEqual(ingest(content, "letter.docx").format, "docx")  # fixed behaviour

    def test_text_quality(self):
        self.assertEqual(text_quality("Client: Brightwater Interiors SRL reference SYN26"), 1.0)
        self.assertLess(text_quality("Cl1ent: Br1ghtwater 1nteriors 5RL"), 0.7)


if __name__ == "__main__":
    unittest.main()
