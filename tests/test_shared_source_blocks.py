"""One renderer for a document block, and one bound on what a request may carry."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from shared.request_budget import RequestBudget, RequestTooLargeError, check_request, image_bytes
from shared.source_blocks import image_inputs, render_block, render_blocks


def block(**overrides):
    fields = dict(
        id="doc/b-0001", doc_id="doc", block_type="table_cell", source_type="itpp",
        content="36 months\nat 2-8 C", heading_stack=["Product", "Shelf life"],
        structural_meta={"page": 3}, image=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


class RenderBlockTests(unittest.TestCase):
    def test_every_block_opens_with_its_address_and_names_its_headings(self):
        """A table cell without its headings said nothing about what lasts 36 months."""
        rendered = render_block(block())
        first, *rest = rendered.splitlines()
        self.assertEqual(first, "[block:doc/b-0001] table_cell | headings: Product > Shelf life")
        self.assertEqual(rest[0], "Source location: page=3")
        self.assertEqual(rest[1:], ["36 months", "at 2-8 C"])

    def test_options_add_what_a_stage_needs_and_nothing_else(self):
        rendered = render_block(block(), document=True, source_type=True, line_numbers=True,
                                groups=lambda b: ["page: 3"])
        self.assertIn("| document: doc | document type: itpp |", rendered)
        self.assertIn("| page: 3", rendered.splitlines()[0])
        self.assertIn("[line:1] 36 months", rendered)
        self.assertIn("[line:2] at 2-8 C", rendered)

    def test_an_image_body_replaces_the_placeholder_only_for_images(self):
        image = block(block_type="image", content="[image]")
        self.assertIn("Cite the visual.", render_block(image, image_body="Cite the visual."))
        self.assertNotIn("[image]", render_block(image, image_body="Cite the visual."))
        self.assertIn("36 months", render_block(block(), image_body="Cite the visual."))

    def test_no_blocks_render_as_none(self):
        self.assertEqual(render_blocks([]), "(none)")


class ImageInputTests(unittest.TestCase):
    def test_images_carry_their_block_id_and_the_stage_detail(self):
        visual = block(image=SimpleNamespace(data_url=lambda: "data:image/png;base64,QUFB"))
        self.assertEqual(image_inputs([block(), visual], detail="low"), [
            {"block_id": "doc/b-0001", "data_url": "data:image/png;base64,QUFB", "detail": "low"},
        ])


class RequestBudgetTests(unittest.TestCase):
    budget = RequestBudget(max_text_chars=10, max_images=1, max_image_bytes=3)

    def test_a_request_inside_its_budget_passes(self):
        check_request("x", text="short", images=[{"data_url": "data:image/png;base64,QUFB"}],
                      budget=self.budget)

    def test_each_limit_refuses_with_its_code_and_subject(self):
        image = {"data_url": "data:image/png;base64,QUFB"}
        for text, images in (("x" * 11, []), ("", [image, image]),
                             ("", [{"data_url": "data:image/png;base64,QUFBQUFB"}])):
            with self.subTest(text=len(text), images=len(images)):
                with self.assertRaises(RequestTooLargeError) as raised:
                    check_request("The selection", text=text, images=images, budget=self.budget)
                self.assertEqual(raised.exception.code, "request_too_large")
                self.assertIn("The selection", str(raised.exception))

    def test_image_bytes_are_counted_without_decoding(self):
        self.assertEqual(image_bytes([{"data_url": "data:image/png;base64,QUFBQUFB"}]), 6)


if __name__ == "__main__":
    unittest.main()
