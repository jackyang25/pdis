"""PDF opt-in produces real citable text, never invented document structure."""

import unittest
import io
import logging
import threading
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from services.chunker import run_pipeline, parse_context_file
from tests.pdf_fixtures import pdf_bytes
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DecodedStreamObject
from pypdf._page import PageObject


class PdfTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "temporary.PDF"

    def parse(self, payload):
        self.path.write_bytes(payload)
        return run_pipeline(
            str(self.path), "study", accepted_suffixes={".docx", ".pptx", ".pdf"},
            org="bmgf", intervention_class="drug", indication="malaria",
        )

    def test_pdf_opt_in_retains_pages_ids_text_and_provenance(self):
        blocks = self.parse(pdf_bytes("The dose is 10 mg.", "The trial is planned."))
        self.assertEqual([b.id for b in blocks], ["study/b-0001", "study/b-0002"])
        self.assertEqual([b.content for b in blocks], ["The dose is 10 mg.", "The trial is planned."])
        self.assertEqual([b.structural_meta["page"] for b in blocks], [1, 2])
        for b in blocks:
            self.assertEqual(b.block_type, "paragraph")
            self.assertEqual(b.heading_stack, [])
            self.assertIsNone(b.section_label)
            self.assertEqual(b.structural_meta["extraction_warnings"], ["pdf_text_only"])
            self.assertEqual((b.org, b.intervention_class, b.indication), ("bmgf", "drug", "malaria"))
        self.assertEqual(blocks, self.parse(pdf_bytes("The dose is 10 mg.", "The trial is planned.")))

    def test_default_pipeline_and_ask_still_refuse_pdf(self):
        self.path.write_bytes(pdf_bytes("Readable text."))
        for parse in (run_pipeline, parse_context_file):
            with self.subTest(parse=parse.__name__), self.assertRaisesRegex(ValueError, "Unsupported"):
                parse(str(self.path), "study")

    def test_one_unreadable_page_refuses_the_whole_document(self):
        with self.assertRaisesRegex(ValueError, "study.*page 2.*no extractable text"):
            self.parse(pdf_bytes("Readable first page.", None, "Readable third page."))

    def test_whitespace_is_not_readable_content(self):
        with self.assertRaisesRegex(ValueError, "no extractable text"):
            self.parse(pdf_bytes("   "))

    def test_image_only_page_is_refused_even_beside_text_pages(self):
        with self.assertRaisesRegex(ValueError, "page 2.*no extractable text"):
            self.parse(pdf_bytes("Readable", None, image_pages=(2,)))

    def test_text_and_image_on_one_page_retains_text_with_limitation(self):
        blocks = self.parse(pdf_bytes("Readable", image_pages=(1,)))
        self.assertEqual(blocks[0].content, "Readable")
        self.assertIsNone(blocks[0].image)
        self.assertEqual(blocks[0].structural_meta["extraction_warnings"], ["pdf_text_only"])

    def test_overlarge_file_is_refused(self):
        with self.assertRaisesRegex(ValueError, "20 MB"):
            self.parse(pdf_bytes("Text") + b" " * (20 * 1024 * 1024))

    def test_overlarge_direct_page_stream_is_refused_before_text_extraction(self):
        with self.assertRaisesRegex(ValueError, "page 1 is too complex"):
            self.parse(pdf_bytes("x" * (5 * 1024 * 1024)))

    def test_encrypted_even_with_empty_password_is_refused(self):
        for password in ("secret", ""):
            with self.subTest(password=password), self.assertRaisesRegex(ValueError, "encrypted"):
                self.parse(pdf_bytes("Readable text.", password=password))

    def test_malformed_or_disguised_pdf_is_refused(self):
        for payload in (b"not a PDF", b"%PDF-1.7\nbroken"):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "study.*readable PDF"):
                self.parse(payload)

    def test_readable_page_with_a_broken_form_is_not_silently_partially_read(self):
        with self.assertRaisesRegex(ValueError, "extraction warnings"):
            self.parse(self.broken_form())

    @staticmethod
    def broken_form():
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(pdf_bytes("Readable text."))).pages[0])
        stream = DecodedStreamObject()
        stream.set_data(page.get_contents().get_data() + b"\n/MissingForm Do")
        page[NameObject("/Contents")] = stream
        payload = io.BytesIO()
        writer.write(payload)
        return payload.getvalue()

    def test_concurrent_parse_warnings_cannot_contaminate_a_readable_document(self):
        good = self.path.parent / "good.pdf"
        bad = self.path.parent / "bad.pdf"
        good.write_bytes(pdf_bytes("Complete text."))
        bad.write_bytes(self.broken_form())
        barrier = threading.Barrier(2)
        original = PageObject.extract_text

        def synchronized_extract(page, *args, **kwargs):
            barrier.wait(timeout=5)
            text = original(page, *args, **kwargs)
            barrier.wait(timeout=5)
            return text

        handlers_before = list(logging.getLogger("pypdf").handlers)
        with patch.object(PageObject, "extract_text", synchronized_extract), ThreadPoolExecutor(2) as pool:
            clean = pool.submit(run_pipeline, str(good), "good", accepted_suffixes={".pdf"})
            broken = pool.submit(run_pipeline, str(bad), "bad", accepted_suffixes={".pdf"})
            self.assertEqual(clean.result()[0].content, "Complete text.")
            with self.assertRaisesRegex(ValueError, "bad.*extraction warnings"):
                broken.result()
        self.assertEqual(logging.getLogger("pypdf").handlers, handlers_before)

    def test_api_log_verbosity_cannot_disable_extraction_validation(self):
        self.path.write_bytes(self.broken_form())
        code = '''
import sys
from api.logging_config import configure_logging
from services.chunker import run_pipeline, TEXT_EXTRACTION_SUFFIXES
configure_logging()
try:
    run_pipeline(sys.argv[1], "study", accepted_suffixes=TEXT_EXTRACTION_SUFFIXES)
except ValueError as exc:
    assert "extraction warnings" in str(exc), str(exc)
else:
    raise AssertionError("Logging verbosity disabled PDF validation")
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                env={**os.environ, "LOG_LEVEL": "ERROR"},
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_pages_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no pages"):
            self.parse(pdf_bytes())

    def test_excessive_page_count_is_refused(self):
        with self.assertRaisesRegex(ValueError, "200 pages"):
            self.parse(pdf_bytes(*(["Page text"] * 201)))
