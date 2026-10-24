from __future__ import annotations

import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pptx import Presentation
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from services.chunker import blocks_to_dicts, run_pipeline
from services.chunker.stages.rasterizer import (
    RendererUnavailableError,
    RenderFailedError,
    render_presentation_slides,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def build_presentation(path: Path) -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Malaria vaccine profile"

    text_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(1.5), Inches(5), Inches(1.2)
    )
    text_box.text_frame.text = "Target population: children"
    second = text_box.text_frame.add_paragraph()
    second.text = "Two-dose primary series"
    second.level = 1

    table = slide.shapes.add_table(
        2, 2, Inches(0.8), Inches(3), Inches(5), Inches(1.2)
    ).table
    table.cell(0, 0).text = "Measure"
    table.cell(0, 1).text = "Target"
    table.cell(1, 0).text = "Efficacy"
    table.cell(1, 1).text = ">= 75%"

    slide.shapes.add_picture(
        BytesIO(PNG_1X1), Inches(6.2), Inches(1.5), width=Inches(1)
    )
    presentation.save(path)


def build_chart_only_presentation(path: Path) -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    data = ChartData()
    data.categories = ["A", "B"]
    data.add_series("Series", (1, 2))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1),
        Inches(6),
        Inches(4),
        data,
    )
    presentation.save(path)


class ChunkerPptxTests(unittest.TestCase):
    def test_slide_renderer_emits_png_when_office_runtime_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.pptx"
            build_presentation(path)
            try:
                rendered = render_presentation_slides(str(path))
            except RendererUnavailableError as exc:
                self.skipTest(str(exc))

        if not rendered:
            self.skipTest("LibreOffice presentation rendering is unavailable")
        self.assertEqual(set(rendered), {1})
        self.assertTrue(rendered[1].startswith(b"\x89PNG\r\n\x1a\n"))

    def test_pptx_emits_text_table_and_one_rendered_slide_visual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.pptx"
            build_presentation(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                return_value={1: PNG_1X1},
            ):
                blocks = run_pipeline(str(path), "profile")

        self.assertEqual(
            [block.id for block in blocks],
            [f"profile/b-{index:04d}" for index in range(len(blocks))],
        )
        self.assertEqual(blocks[0].block_type, "heading")
        self.assertEqual(blocks[0].content, "Malaria vaccine profile")
        self.assertEqual(
            [block.content for block in blocks].count("Malaria vaccine profile"), 1
        )
        self.assertIn("x", blocks[0].structural_meta)
        self.assertTrue(
            any(block.content == "Target population: children" for block in blocks)
        )
        table_row = next(block for block in blocks if block.block_type == "table_row")
        self.assertEqual(table_row.content, "Measure: Efficacy, Target: >= 75%")
        self.assertEqual(
            table_row.structural_meta["table_cells"],
            [
                {
                    "column_index": 0,
                    "header": "Measure",
                    "value": "Efficacy",
                    "content_start": 0,
                    "content_end": 17,
                    "value_start": 9,
                    "value_end": 17,
                },
                {
                    "column_index": 1,
                    "header": "Target",
                    "value": ">= 75%",
                    "content_start": 19,
                    "content_end": 33,
                    "value_start": 27,
                    "value_end": 33,
                },
            ],
        )
        image_blocks = [block for block in blocks if block.block_type == "image"]
        self.assertEqual(len(image_blocks), 1)
        image = image_blocks[0]
        self.assertEqual(image.structural_meta["slide"], 1)
        self.assertEqual(image.structural_meta["visual_scope"], "full_slide")
        self.assertIsNotNone(image.image)
        assert image.image is not None
        self.assertEqual(image.image.media_type, "image/png")
        self.assertIn("presentationml.presentation", image.image.source_media_type)
        self.assertEqual(base64.b64decode(image.image.data_base64), PNG_1X1)
        self.assertTrue(
            all("extraction_warnings" not in block.structural_meta for block in blocks)
        )

    def test_pptx_unavailable_renderer_fallback_is_portable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.pptx"
            build_presentation(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                side_effect=RendererUnavailableError("LibreOffice is unavailable"),
            ):
                blocks = run_pipeline(str(path), "profile")

        image_blocks = [block for block in blocks if block.block_type == "image"]
        self.assertEqual(len(image_blocks), 1)
        image = image_blocks[0]
        self.assertEqual(image.structural_meta["visual_scope"], "embedded_picture")
        self.assertIsNotNone(image.image)
        assert image.image is not None
        self.assertEqual(image.image.source_media_type, "image/png")
        self.assertTrue(all(
            block.structural_meta["extraction_warnings"]
            == ["presentation_renderer_unavailable"]
            for block in blocks
        ))
        serialized = blocks_to_dicts(blocks)
        self.assertEqual(
            serialized[0]["structural_meta"]["extraction_warnings"],
            ["presentation_renderer_unavailable"],
        )

    def test_pptx_failed_renderer_fallback_has_a_distinct_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.pptx"
            build_presentation(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                side_effect=RenderFailedError("conversion timed out"),
            ):
                blocks = run_pipeline(str(path), "profile")

        self.assertTrue(all(
            block.structural_meta["extraction_warnings"]
            == ["presentation_render_failed"]
            for block in blocks
        ))
        image_blocks = [block for block in blocks if block.block_type == "image"]
        self.assertEqual(len(image_blocks), 1)
        self.assertEqual(image_blocks[0].structural_meta["visual_scope"], "embedded_picture")

    def test_chart_only_pptx_refuses_a_blockless_degraded_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart-only.pptx"
            build_chart_only_presentation(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                side_effect=RendererUnavailableError("LibreOffice is unavailable"),
            ), self.assertRaisesRegex(
                ValueError,
                "chart-only.*presentation_renderer_unavailable.*no retained content",
            ):
                run_pipeline(str(path), "chart-only")


    def test_hidden_slide_is_rendered_and_marked(self) -> None:
        presentation = Presentation()
        for title in ("Shown", "Hidden backup", "Also shown"):
            slide = presentation.slides.add_slide(presentation.slide_layouts[5])
            slide.shapes.title.text = title
        presentation.slides[1]._element.set("show", "0")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hidden.pptx"
            presentation.save(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                return_value={1: PNG_1X1, 2: PNG_1X1, 3: PNG_1X1},
            ):
                blocks = run_pipeline(str(path), "hidden")

        renders = [block for block in blocks if block.block_type == "image"]
        self.assertEqual([block.structural_meta["slide"] for block in renders], [1, 2, 3])
        self.assertEqual(
            {block.structural_meta["slide"] for block in blocks
             if block.structural_meta.get("slide_hidden")},
            {2},
        )
        self.assertTrue(all("extraction_warnings" not in block.structural_meta for block in blocks))

    def test_unrendered_chart_is_flagged_like_a_docx_visual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.pptx"
            build_chart_only_presentation(path)
            presentation = Presentation(path)
            presentation.slides[0].shapes.add_textbox(
                Inches(1), Inches(6), Inches(4), Inches(1)
            ).text_frame.text = "Efficacy by age group"
            presentation.save(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                side_effect=RendererUnavailableError("LibreOffice is unavailable"),
            ):
                blocks = run_pipeline(str(path), "chart")

        flagged = [
            block for block in blocks
            if "unsupported_document_visual" in block.structural_meta["extraction_warnings"]
        ]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].block_type, "image")
        self.assertIsNone(flagged[0].image)
        self.assertEqual(flagged[0].structural_meta["unsupported_visual_kind"], "chart")
        self.assertEqual(flagged[0].structural_meta["slide"], 1)
        self.assertIn("shape_path", flagged[0].structural_meta)
        self.assertIn(
            "presentation_renderer_unavailable",
            flagged[0].structural_meta["extraction_warnings"],
        )

    def test_grouped_shape_positions_are_slide_relative(self) -> None:
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        group = slide.shapes.add_group_shape()
        box = group.shapes.add_textbox(0, 0, Inches(2), Inches(1))
        box.text_frame.text = "Grouped label"
        xfrm = group._element.grpSpPr.get_or_add_xfrm()
        # The group is drawn at (5in, 3in) at half its children's size.
        xfrm.get_or_add_off().x, xfrm.get_or_add_off().y = Inches(5), Inches(3)
        xfrm.get_or_add_ext().cx, xfrm.get_or_add_ext().cy = Inches(1), Inches(0.5)
        xfrm.get_or_add_chOff().x, xfrm.get_or_add_chOff().y = 0, 0
        xfrm.get_or_add_chExt().cx, xfrm.get_or_add_chExt().cy = Inches(2), Inches(1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "group.pptx"
            presentation.save(path)
            with patch(
                "services.chunker.stages.parser_pptx.render_presentation_slides",
                return_value={1: PNG_1X1},
            ):
                blocks = run_pipeline(str(path), "group")

        label = next(block for block in blocks if block.content == "Grouped label")
        meta = label.structural_meta
        self.assertAlmostEqual(meta["x"], Inches(5) / presentation.slide_width, places=3)
        self.assertAlmostEqual(meta["y"], Inches(3) / presentation.slide_height, places=3)
        self.assertAlmostEqual(meta["width"], Inches(1) / presentation.slide_width, places=3)
        self.assertAlmostEqual(meta["height"], Inches(0.5) / presentation.slide_height, places=3)


if __name__ == "__main__":
    unittest.main()
