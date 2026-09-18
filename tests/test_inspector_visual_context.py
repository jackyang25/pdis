"""A slide overview supplies context without changing section ownership."""

import unittest

from services.chunker import ContentBlock, ImageAsset
from services.inspector.source_context import with_slide_overviews


def block(name, slide, *, visual=False, doc_id="deck"):
    return ContentBlock(
        id=f"{doc_id}/{name}", doc_id=doc_id, ordinal=0,
        block_type="image" if visual else "paragraph",
        content="[image]" if visual else name, heading_stack=[], style_hint={},
        structural_meta={"slide": slide, **({"visual_scope": "full_slide"} if visual else {})},
        image=ImageAsset(media_type="image/png", data_base64="AA==", sha256="test",
                         source_media_type="image/png", width=1, height=1) if visual else None,
    )


class InspectorVisualContextTests(unittest.TestCase):
    def test_assessment_and_contract_share_visual_scope_without_remapping(self):
        from services.inspector.stages.assessor import assess_document
        from services.inspector.contract import validate_result_contract
        from tests.test_inspector_contract import _config, _result

        text = block("target", 1)
        text.doc_id = "document"
        text.id = "document:b1"
        text.section_label = "Profile"
        overview = block("overview", 1, visual=True, doc_id="document")
        overview.section_label = "Other"
        source = [text, overview]
        calls = []

        class Client:
            def call_structured(self, _system, _message, *_args, schema, **kwargs):
                calls.append((schema, kwargs))
                return {"verdict": "specified", "statement": "", "block_ids": [overview.id]}

        config = _config()
        assessments, mapped = assess_document(source, config, Client(), max_tokens=1000)
        self.assertEqual(mapped, {"Profile": [text.id]})
        self.assertEqual(len(calls), 2)
        for schema, kwargs in calls:
            self.assertIn(overview.id, schema["properties"]["block_ids"]["items"]["enum"])
            self.assertEqual(kwargs["images"][0]["block_id"], overview.id)
        result = _result(config, assessments, blocks=source, mapped=mapped)
        self.assertIs(validate_result_contract(result, config), result)
        overview.structural_meta["slide"] = 2
        with self.assertRaisesRegex(ValueError, "outside its scope"):
            validate_result_contract(result, config)

    def test_only_retained_same_slide_overviews_are_added_in_source_order(self):
        text = block("target", 1)
        unrelated = block("other-text", 1)
        overview = block("overview", 1, visual=True)
        another_slide = block("next", 2, visual=True)
        another_document = block("other-deck", 1, visual=True, doc_id="other")
        missing = block("missing", 1, visual=True)
        missing.image = None
        source = [text, unrelated, overview, another_slide, another_document, missing]
        self.assertEqual(with_slide_overviews([text], source), [text, overview])
        self.assertIsNone(overview.section_label)
        self.assertEqual(with_slide_overviews([], source), [])

    def test_already_selected_overview_is_not_duplicated(self):
        text = block("target", 1)
        overview = block("overview", 1, visual=True)
        self.assertEqual(with_slide_overviews([text, overview], [text, overview]), [text, overview])
