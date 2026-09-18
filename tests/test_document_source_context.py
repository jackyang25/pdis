import unittest

from shared.document_metadata import extraction_context
from services.chunker import ContentBlock
from services.aligner.context import format_blocks
from services.inspector.stages.assessor import _format_blocks
from services.scout.context import render_document_context, rendered_block_texts


class SourceContextTests(unittest.TestCase):
    def test_unsupported_object_identity_reaches_model_context(self):
        context = extraction_context({
            "unsupported_visual_kind": "drawing", "document_part_kind": "header",
            "extraction_warnings": ["unsupported_document_visual"],
        })
        self.assertIn("unsupported_visual_kind=drawing", context)
        self.assertIn("document_part_kind=header", context)

    def test_explicit_docx_part_context_has_no_guessed_page(self):
        rendered = extraction_context({"document_part": "/word/footnotes.xml",
                                       "document_part_kind": "footnote", "note_id": "2"})
        self.assertIn("document_part_kind=footnote", rendered)
        self.assertIn("note_id=2", rendered)
        self.assertNotIn("page=", rendered)

    def test_scout_visual_marker_is_not_exact_target_text(self):
        block = ContentBlock(
            id="deck/image", doc_id="deck", ordinal=0, block_type="image",
            content="[image]", heading_stack=[], structural_meta={}, style_hint={},
        )
        rendered = render_document_context([block])
        self.assertIn("deck/image", rendered)
        self.assertEqual(rendered_block_texts(rendered), {})

    def test_metadata_with_unknown_visual_shape_remains_readable(self):
        self.assertEqual(extraction_context({"visual_scope": []}), "")

    def test_source_location_and_degraded_visual_coverage_reach_readers(self):
        block = ContentBlock(
            id="deck/b-1", doc_id="deck", ordinal=0, block_type="paragraph",
            content="The dose is 10 mg.", heading_stack=[],
            structural_meta={"slide": 2, "extraction_warnings": ["presentation_render_failed"]},
            style_hint={},
        )
        for render in (format_blocks, _format_blocks, render_document_context):
            with self.subTest(render=render.__module__):
                rendered = render([block])
                self.assertIn("slide=2", rendered)
                self.assertIn("presentation_render_failed", rendered)
                self.assertIn("The dose is 10 mg.", rendered)
        self.assertEqual(rendered_block_texts(render_document_context([block])),
                         {"deck/b-1": "The dose is 10 mg."})

    def test_new_pdf_warning_does_not_claim_rendered_visuals_are_missing(self):
        result = extraction_context({"page": 4, "extraction_warnings": ["pdf_text_layout"]})
        self.assertIn("page=4", result)
        self.assertIn("reading order", result)
        self.assertNotIn("Vector drawings and images nested", result)

    def test_historical_warning_keeps_its_original_extraction_meaning(self):
        result = extraction_context({"extraction_warnings": ["pdf_limited_structure"]})
        self.assertIn("not read", result)
