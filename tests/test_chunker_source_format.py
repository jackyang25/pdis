"""Every block says which kind of file it was parsed from.

Readers used to have no way to say a passage came from slides or a PDF except by
inspecting whatever else a block held - a page number, a slide number - which is an
inference about the parser rather than a fact it recorded. The dispatch that chooses a
parser by extension now stamps that extension's format on every block it returns.
"""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services.chunker.formats import (
    SOURCE_FORMAT_BY_SUFFIX,
    SOURCE_FORMATS,
    TEXT_EXTRACTION_SUFFIXES,
)
from services.chunker.models import ContentBlock
from services.chunker.pipeline import parse_context_file
from services.chunker.stages import parser


def _block(doc_id: str) -> ContentBlock:
    return ContentBlock(
        id=f"{doc_id}/b-0001", doc_id=doc_id, ordinal=1, block_type="paragraph",
        content="Text.", heading_stack=[], structural_meta={}, style_hint={},
    )


class SourceFormatTests(unittest.TestCase):
    def test_every_accepted_suffix_names_a_format(self) -> None:
        self.assertEqual(set(SOURCE_FORMAT_BY_SUFFIX), set(TEXT_EXTRACTION_SUFFIXES))
        self.assertLessEqual(set(SOURCE_FORMAT_BY_SUFFIX.values()), SOURCE_FORMATS)

    def test_the_dispatch_stamps_the_format_of_the_parser_it_chose(self) -> None:
        for suffix, expected in SOURCE_FORMAT_BY_SUFFIX.items():
            name = {".docx": "parse_docx", ".pptx": "parse_pptx", ".pdf": "parse_pdf"}[suffix]
            with patch.object(parser, name, side_effect=lambda path, doc_id: [_block(doc_id), _block(doc_id)]):
                blocks = parser.parse_document(f"plan{suffix}", "plan", accepted_suffixes=TEXT_EXTRACTION_SUFFIXES)
            self.assertEqual({block.source_format for block in blocks}, {expected}, suffix)

    def test_a_standalone_image_attachment_is_an_image(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.png"
            path.write_bytes(buffer.getvalue())
            (block,) = parse_context_file(str(path), "chart", source_media_type="image/png")
        self.assertEqual(block.source_format, "image")
        self.assertTrue(base64.b64decode(block.image.data_base64))


if __name__ == "__main__":
    unittest.main()
