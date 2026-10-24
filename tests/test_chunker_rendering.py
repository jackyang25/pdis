from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services.chunker.stages import rasterizer
from services.chunker.stages.image_assets import image_assets_from_bytes
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

    def test_png_encoding_runs_outside_the_pdfium_lock(self) -> None:
        held_during_encode: list[bool] = []
        original_save = Image.Image.save

        def observing_save(image, *args, **kwargs):
            held_during_encode.append(rasterizer._pdfium_lock.locked())
            return original_save(image, *args, **kwargs)

        with patch.object(Image.Image, "save", observing_save):
            rendered = self.render(pdf_bytes("First", "Second"))

        self.assertEqual(set(rendered), {1, 2})
        self.assertEqual(held_during_encode, [False, False])


class OfficeProcessTests(unittest.TestCase):
    def test_timeout_kills_the_whole_office_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            with self.assertRaises(subprocess.TimeoutExpired):
                rasterizer._run_office(
                    ["sh", "-c", f"sleep 30 & echo $! > {pid_file}; wait"],
                    timeout=1,
                )
            child = int(pid_file.read_text().strip())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _alive(child):
            time.sleep(0.05)
        self.assertFalse(_alive(child), "the converter's child process survived")

    def test_vector_images_share_one_office_start_and_repeats_convert_once(self) -> None:
        calls: list[list[str]] = []

        def fake_office(arguments, *, timeout):
            calls.append(arguments)
            outdir = arguments[arguments.index("--outdir") + 1]
            for source in arguments[arguments.index("--outdir") + 2:]:
                output = BytesIO()
                Image.new("RGB", (2, 2), "white").save(output, format="PNG")
                (Path(outdir) / f"{Path(source).stem}.png").write_bytes(output.getvalue())

        with patch.object(rasterizer, "_soffice_path", return_value="soffice"), patch.object(
            rasterizer, "_run_office", side_effect=fake_office
        ):
            assets = image_assets_from_bytes([
                (b"emf logo", "image/x-emf"),
                (b"wmf chart", "image/x-wmf"),
                (b"emf logo", "image/x-emf"),
            ])

        self.assertEqual(len(calls), 1)
        sources = calls[0][calls[0].index("--outdir") + 2:]
        self.assertEqual(len(sources), 2)
        self.assertTrue(all(asset is not None for asset in assets))
        self.assertEqual(assets[0].sha256, assets[2].sha256)
        self.assertIsNot(assets[0], assets[2])
        self.assertEqual({asset.source_media_type for asset in assets}, {"image/x-emf", "image/x-wmf"})

    def test_presentation_export_includes_hidden_slides(self) -> None:
        calls: list[list[str]] = []

        def fake_office(arguments, *, timeout):
            calls.append(arguments)
            outdir = Path(arguments[arguments.index("--outdir") + 1])
            (outdir / "deck.pdf").write_bytes(pdf_bytes("Slide"))

        with patch.object(rasterizer, "_soffice_path", return_value="soffice"), patch.object(
            rasterizer, "_run_office", side_effect=fake_office
        ):
            rendered = rasterizer.render_presentation_slides("/tmp/deck.pptx")

        self.assertEqual(set(rendered), {1})
        target = calls[0][calls[0].index("--convert-to") + 1]
        self.assertTrue(target.startswith("pdf:impress_pdf_Export:"))
        self.assertIn('"ExportHiddenSlides"', target)


def _alive(pid: int) -> bool:
    try:
        finished, _ = os.waitpid(pid, os.WNOHANG)
        if finished == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        status = Path(f"/proc/{pid}/stat").read_text().split()[2]
    except OSError:
        return True
    return status != "Z"


if __name__ == "__main__":
    unittest.main()
