"""One set of document formats for every tool, read by one reader per format.

DOCX, PPTX and XLSX declare their structure, so a block's structure is read rather than
inferred. PDF is accepted as page text, its limit carried on every block it produces; a
format outside the set is refused at the parser boundary, naming the set.
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
    def test_the_supported_set_is_the_four_formats_and_their_legacy_forms(self) -> None:
        self.assertEqual(DOCUMENT_SUFFIXES, {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".pdf"})

    def test_every_legacy_format_converts_to_a_format_with_its_own_reader(self) -> None:
        from services.chunker.formats import LEGACY_SUFFIXES
        from services.chunker.stages.parser import _PARSERS

        self.assertEqual(set(LEGACY_SUFFIXES), DOCUMENT_SUFFIXES - set(_PARSERS))
        self.assertLessEqual(set(LEGACY_SUFFIXES.values()), set(_PARSERS))

    def test_a_format_outside_the_set_is_refused_naming_the_set(self) -> None:
        with self.assertRaises(ValueError) as caught:
            parse_document("profile.rtf", "profile")
        supported = str(caught.exception).split("Supported:", 1)[1]
        for suffix in DOCUMENT_SUFFIXES:
            self.assertIn(suffix, supported)


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
        for suffix in (".docx", ".pptx", ".xlsx"):
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
