"""Models see parser-authored limitations, not text stripped of its provenance."""

import unittest
from dataclasses import asdict

from services.assistant import document
from services.chunker import ContentBlock
from services.screener.stages.assessor import _format_blocks


class ExtractionContextTests(unittest.TestCase):
    def setUp(self):
        self.block = ContentBlock(
            id="study/b-0002", doc_id="study", ordinal=2, block_type="paragraph",
            content="The trial is planned.", heading_stack=[], style_hint={},
            structural_meta={"page": 2, "extraction_warnings": ["pdf_text_only"]},
        )

    def test_ask_exposes_page_and_limitations_in_overview_and_reads(self):
        blocks = [asdict(self.block)]
        for text in (document.overview(blocks), document.get(blocks, [self.block.id]),
                     document.get_range(blocks, "study"), document.find(blocks, "trial")):
            with self.subTest(text=text):
                self.assertIn("pdf_text_only", text)
                self.assertIn("Images", text)
                self.assertIn("page", text.lower())

    def test_screener_assessment_sees_limitations_beside_source_text(self):
        message = _format_blocks([self.block])
        self.assertIn("The trial is planned.", message)
        self.assertIn("pdf_text_only", message)
        self.assertIn("Images", message)
        self.assertIn("page", message.lower())
