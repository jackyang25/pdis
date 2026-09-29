"""The image label every model call uses. Tool pipelines depend on its exact text."""

import unittest

from shared.openai_client import _user_content
from shared.visuals import labelled_image_parts


class LabelledImageTests(unittest.TestCase):
    def test_label_names_the_exact_block_and_keeps_high_detail(self):
        self.assertEqual(labelled_image_parts([("deck/b-0004", "data:image/png;base64,AAAA")]), [
            {"type": "text", "text": "Visual for document block [deck/b-0004]:"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ])

    def test_tool_pipeline_payload_is_unchanged(self):
        # Byte-for-byte what `_user_content` produced before the helper was extracted.
        self.assertEqual(
            _user_content("Assess", [{"block_id": "d/b-1", "data_url": "data:image/png;base64,QQ"}]),
            [
                {"type": "text", "text": "Assess"},
                {"type": "text", "text": "Visual for document block [d/b-1]:"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QQ", "detail": "high"}},
            ],
        )
        self.assertEqual(_user_content("Assess", None), "Assess")
