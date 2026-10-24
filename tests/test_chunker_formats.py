"""Only formats that declare their own structure are accepted.

DOCX and PPTX state tables, rows, and headings in the file itself, so a parsed
block's structure is read rather than inferred. A rendering format carries glyph
positions only, and reconstructing structure from geometry can merge unrelated
table columns into one block whose text still passes exact-quote validation. The
suite refuses that class of silent provenance error at the format boundary.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile

from services.chunker import find_config
from services.chunker.models import CONFIGS_DIR
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


class UnreadableDocumentTests(unittest.TestCase):
    """A corrupt upload is the caller's input error, not a server failure."""

    def test_a_corrupt_package_is_a_value_error_naming_the_document(self) -> None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("notes.txt", "not an Office package")
        payloads = {
            "not a zip": b"not really a document",
            "a zip without its parts": archive.getvalue(),
            "a truncated zip": archive.getvalue()[:40],
        }
        for suffix in (".docx", ".pptx"):
            for case, payload in payloads.items():
                with self.subTest(suffix=suffix, case=case):
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                        handle.write(payload)
                    self.addCleanup(os.unlink, handle.name)
                    with self.assertRaises(ValueError) as caught:
                        parse_document(handle.name, "profile")
                    message = str(caught.exception)
                    self.assertIn("profile", message)
                    # The temporary path is not the reader's file.
                    self.assertNotIn(handle.name, message)


class ConfigLookupTests(unittest.TestCase):
    def test_a_key_cannot_reach_outside_the_configs(self) -> None:
        """The keys come from a request; a path built from them could name any file."""
        config = find_config("bmgf", "itpp", "vaccine")
        for org in ("../configs/bmgf", "x/../bmgf"):
            with self.subTest(org=org):
                with self.assertRaises(LookupError) as caught:
                    find_config(org, config.source_type, config.intervention_class)
                self.assertNotIn(str(CONFIGS_DIR), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
