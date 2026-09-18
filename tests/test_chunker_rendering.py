from __future__ import annotations

import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services.chunker.stages.rasterizer import (
    RenderFailedError,
    RenderLimitError,
    render_pdf_pages,
)
from tests.pdf_fixtures import pdf_bytes


class BoundedRenderingTests(unittest.TestCase):
    def render(self, payload: bytes) -> dict[int, bytes]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pdf"
            path.write_bytes(payload)
            return render_pdf_pages(str(path))

    def test_page_count_past_render_limit_is_refused(self) -> None:
        with patch(
            "services.chunker.stages.rasterizer.MAX_RENDER_PAGES", 1
        ), self.assertRaisesRegex(RenderLimitError, "1-page limit"):
            self.render(pdf_bytes("First", "Second"))

    def test_page_over_pixel_budget_is_refused_before_rendering(self) -> None:
        with patch(
            "services.chunker.stages.rasterizer.MAX_RENDER_PIXELS_PER_PAGE", 1
        ), self.assertRaisesRegex(RenderLimitError, "per-page pixel limit"):
            self.render(pdf_bytes("Readable"))

    def test_aggregate_encoded_image_budget_refuses_partial_output(self) -> None:
        with patch(
            "services.chunker.stages.rasterizer.MAX_RENDERED_BYTES", 1
        ), self.assertRaisesRegex(RenderLimitError, "aggregate encoded-image limit"):
            self.render(pdf_bytes("Readable"))

    def test_page_count_must_match_the_declared_source_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one-page.pdf"
            path.write_bytes(pdf_bytes("Only page"))
            with self.assertRaisesRegex(
                RenderFailedError, "produced 1 pages; expected 2"
            ):
                render_pdf_pages(str(path), expected_pages=2)

    def test_non_positive_page_dimensions_are_a_typed_render_failure(self) -> None:
        class ZeroWidthPage:
            get_width = lambda self: 0
            get_height = lambda self: 792
            close = lambda self: None

            def render(self, **kwargs):
                raise AssertionError("invalid dimensions must be refused before rendering")

        class OnePageDocument:
            def __len__(self):
                return 1

            def __getitem__(self, index):
                return ZeroWidthPage()

            def close(self):
                pass

        fake_pdfium = types.SimpleNamespace(PdfDocument=lambda path: OnePageDocument())
        with patch.dict("sys.modules", {"pypdfium2": fake_pdfium}), self.assertRaisesRegex(
            RenderFailedError, "invalid dimensions"
        ):
            render_pdf_pages("unused.pdf")

    def test_pdfium_rendering_is_globally_serialized(self) -> None:
        tracker_lock = threading.Lock()
        active = 0
        maximum_active = 0

        class Bitmap:
            def to_pil(self):
                return Image.new("RGB", (10, 10), "white")

            def close(self):
                pass

        class Page:
            def get_width(self):
                return 10

            def get_height(self):
                return 10

            def render(self, **kwargs):
                nonlocal active, maximum_active
                with tracker_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.05)
                with tracker_lock:
                    active -= 1
                return Bitmap()

            def close(self):
                pass

        class Document:
            def __len__(self):
                return 1

            def __getitem__(self, index):
                return Page()

            def close(self):
                pass

        fake_pdfium = types.SimpleNamespace(PdfDocument=lambda path: Document())
        with patch.dict("sys.modules", {"pypdfium2": fake_pdfium}), ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            results = list(pool.map(render_pdf_pages, ("first.pdf", "second.pdf")))

        self.assertEqual([set(result) for result in results], [{1}, {1}])
        self.assertEqual(maximum_active, 1)


if __name__ == "__main__":
    unittest.main()
