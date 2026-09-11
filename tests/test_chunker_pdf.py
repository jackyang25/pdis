"""PDF opt-in produces real citable text, never invented document structure."""

import unittest
import io
import base64
from PIL import Image
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
from pypdf.generic import NameObject, DecodedStreamObject, DictionaryObject, NumberObject, ArrayObject
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
            self.assertEqual(b.structural_meta["extraction_warnings"], ["pdf_limited_structure"])
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

    def test_pdf_images_are_portable_citable_blocks_without_changing_text_ids(self):
        payload = pdf_bytes("Readable", "Next page", image_pages=(1, 2))
        blocks = self.parse(payload)
        self.assertEqual([b.id for b in blocks], [
            "study/b-0001", "study/b-0001-image-0001",
            "study/b-0002", "study/b-0002-image-0001",
        ])
        self.assertEqual([b.ordinal for b in blocks], [1, 2, 3, 4])
        self.assertEqual(blocks[0].content, "Readable")
        self.assertIsNone(blocks[0].image)
        for block, page in ((blocks[1], 1), (blocks[3], 2)):
            self.assertEqual(block.block_type, "image")
            self.assertEqual(block.structural_meta["page"], page)
            self.assertEqual(block.structural_meta["extraction_warnings"], ["pdf_limited_structure"])
            self.assertEqual(block.org, "bmgf")
            self.assertIsNone(block.source_type)
            self.assertEqual((block.image.width, block.image.height), (1, 1))
            with Image.open(io.BytesIO(base64.b64decode(block.image.data_base64))) as image:
                self.assertEqual(image.convert("RGB").getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(blocks, self.parse(payload))

    def test_overlarge_file_is_refused(self):
        with self.assertRaisesRegex(ValueError, "20 MB"):
            self.parse(pdf_bytes("Text") + b" " * (20 * 1024 * 1024))

    def test_embedded_jpeg_bytes_are_preserved_and_citable(self):
        jpeg = io.BytesIO()
        Image.new("RGB", (12, 8), "blue").save(jpeg, format="JPEG")
        blocks = self.parse(self.jpeg_pdf(jpeg.getvalue()))
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1].image.media_type, "image/jpeg")
        self.assertEqual(base64.b64decode(blocks[1].image.data_base64), jpeg.getvalue())
        self.assertEqual((blocks[1].image.width, blocks[1].image.height), (12, 8))

    def test_corrupt_embedded_image_refuses_document_instead_of_losing_evidence(self):
        with self.assertRaisesRegex(ValueError, "study.*readable PDF"):
            self.parse(self.jpeg_pdf(b"not a jpeg"))

    def test_unused_image_resources_are_not_citable_page_evidence(self):
        jpeg = io.BytesIO()
        Image.new("RGB", (12, 8), "blue").save(jpeg, format="JPEG")
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(self.jpeg_pdf(jpeg.getvalue()))).pages[0])
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 50 700 Td (Text only.) Tj ET")
        page[NameObject("/Contents")] = content
        payload = io.BytesIO()
        writer.write(payload)
        self.assertEqual([b.block_type for b in self.parse(payload.getvalue())], ["paragraph"])

    def test_invalid_image_dimensions_follow_the_input_error_contract(self):
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(self.jpeg_pdf(b"invalid"))).pages[0])
        page["/Resources"]["/XObject"]["/Photo"][NameObject("/Width")] = NumberObject(0)
        payload = io.BytesIO()
        writer.write(payload)
        with self.assertRaisesRegex(ValueError, "study.*readable PDF"):
            self.parse(payload.getvalue())

    def test_nested_form_images_are_explicitly_outside_the_extraction_contract(self):
        jpeg = io.BytesIO()
        Image.new("RGB", (12, 8), "blue").save(jpeg, format="JPEG")
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(self.jpeg_pdf(jpeg.getvalue()))).pages[0])
        form = DecodedStreamObject()
        form.set_data(b"q 12 0 0 8 0 0 cm /Photo Do Q")
        form.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 12, 8)]),
            NameObject("/Resources"): DictionaryObject({
                NameObject("/XObject"): page["/Resources"]["/XObject"],
            }),
        })
        page["/Resources"][NameObject("/XObject")] = DictionaryObject({
            NameObject("/Group"): writer._add_object(form),
        })
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 50 700 Td (Grouped figure.) Tj ET /Group Do")
        page[NameObject("/Contents")] = content
        payload = io.BytesIO()
        writer.write(payload)
        blocks = self.parse(payload.getvalue())
        self.assertEqual([b.block_type for b in blocks], ["paragraph"])
        from shared.document_metadata import extraction_context
        self.assertIn("images nested in Form objects are not read", extraction_context(blocks[0].structural_meta))

    @staticmethod
    def jpeg_pdf(data):
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(pdf_bytes("Figure follows."))).pages[0])
        picture = DecodedStreamObject()
        picture.set_data(data)
        picture.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(12),
            NameObject("/Height"): NumberObject(8),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/Filter"): NameObject("/DCTDecode"),
        })
        page["/Resources"][NameObject("/XObject")] = DictionaryObject({
            NameObject("/Photo"): writer._add_object(picture),
        })
        content = DecodedStreamObject()
        content.set_data(page.get_contents().get_data() + b"\nq 12 0 0 8 50 50 cm /Photo Do Q")
        page[NameObject("/Contents")] = content
        payload = io.BytesIO()
        writer.write(payload)
        return payload.getvalue()

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
