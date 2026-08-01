"""Every config's declared identity matches the filename it is selected by.

A `(org, source_type, intervention_class)` triple is stated twice: once in the
filename, which is how the triple is resolved to a path, and once in the file's
own fields, which become output provenance. Nothing forces the two to agree.

Chunker enumerates the document types the whole picker offers, and it builds each
entry from the *declared* fields while Inspector and Scout are then looked up by
those values as *filenames*. A file that disagreed with its own name would
therefore list one identity and load another, with no error on either side.

Scout validates this at load time and Inspector validates part of it. This test
covers all three uniformly so the guarantee does not depend on which service a
config belongs to.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
# Aligner is absent deliberately: it owns one source-type-neutral configuration
# rather than a file per triple, so it has no identity to keep in sync.
SERVICES = ("chunker", "inspector", "scout")
IDENTITY_FIELDS = ("org", "source_type", "intervention_class")


def _config_paths(service: str) -> list[Path]:
    directory = REPO_ROOT / "services" / service / "configs"
    return sorted(
        path
        for path in directory.glob("*.yaml")
        # Scaffolds and shared methodology files are not document types. A type
        # config is named for its triple, so anything that is not a
        # lowercase three-part stem is not one.
        if "TEMPLATE" not in path.stem.upper()
        and path.stem == path.stem.lower()
        and len(path.stem.split("_")) == 3
    )


class ConfigIdentityTests(unittest.TestCase):
    def test_every_config_declares_the_identity_it_is_named_for(self) -> None:
        checked = 0
        for service in SERVICES:
            for path in _config_paths(service):
                with self.subTest(config=f"{service}/{path.name}"):
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    expected = path.stem.split("_")
                    declared = [data.get(field) for field in IDENTITY_FIELDS]
                    self.assertEqual(
                        declared,
                        expected,
                        f"{path.name} is selected as {expected} but declares {declared}",
                    )
                    self.assertEqual(
                        data.get("type_key"),
                        path.stem,
                        f"{path.name} declares type_key {data.get('type_key')!r}",
                    )
                    checked += 1
        self.assertTrue(checked, "no document type configs were discovered")

    def test_the_document_tools_cover_the_same_triples(self) -> None:
        """A triple Chunker offers must be resolvable by whoever claims it.

        Coverage may legitimately differ — an Inspector rubric is optional, and
        the API probes for it. What must not differ is the *spelling* of a triple
        the services share, which is what an unnoticed rename produces.
        """
        by_service = {
            service: {path.stem for path in _config_paths(service)}
            for service in SERVICES
        }
        for service, stems in by_service.items():
            if service == "chunker":
                continue
            with self.subTest(service=service):
                unknown = sorted(stems - by_service["chunker"])
                self.assertEqual(
                    unknown,
                    [],
                    f"{service} configures triples the chunker cannot parse: {unknown}",
                )


if __name__ == "__main__":
    unittest.main()
