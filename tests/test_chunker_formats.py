"""Only formats that declare their own structure are accepted.

DOCX and PPTX state tables, rows, and headings in the file itself, so a parsed
block's structure is read rather than inferred. A rendering format carries glyph
positions only, and reconstructing structure from geometry can merge unrelated
table columns into one block whose text still passes exact-quote validation. The
suite refuses that class of silent provenance error at the format boundary.
"""

from __future__ import annotations

import unittest

from services.chunker.pipeline import DOCUMENT_SUFFIXES
from services.chunker.stages.parser import parse_document


class SupportedFormatTests(unittest.TestCase):
    def test_declared_structure_formats_are_the_supported_set(self) -> None:
        self.assertEqual(DOCUMENT_SUFFIXES, {".docx", ".pptx"})

    def test_a_rendering_format_is_rejected_at_the_parser_boundary(self) -> None:
        with self.assertRaises(ValueError) as caught:
            parse_document("profile.pdf", "profile")

        message = str(caught.exception)
        self.assertIn(".pdf", message)
        self.assertIn(".docx", message)
        self.assertIn(".pptx", message)

    def test_the_error_names_only_supported_formats_as_available(self) -> None:
        with self.assertRaises(ValueError) as caught:
            parse_document("profile.rtf", "profile")

        supported = str(caught.exception).split("Supported:", 1)[1]
        self.assertNotIn(".pdf", supported)


if __name__ == "__main__":
    unittest.main()
