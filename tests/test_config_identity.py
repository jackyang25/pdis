"""Every service agrees on which document types exist and what they are called.

A `(org, source_type, intervention_class)` triple is stated twice: in the
filename that resolves it to a path, and in the file's own fields, which become
output provenance. Chunker enumerates the types the whole picker offers and
builds each entry from the *declared* fields, while Inspector and Scout are then
looked up by those values as *filenames* - so a file disagreeing with its own
name would list one identity and load another.

These tests ask each service what it has rather than reading its config
directory. Deciding what counts as a config from the shape of a filename would
be a second rule, in a test, competing with the one the services enforce.
"""

from __future__ import annotations

import unittest

from services import chunker, inspector, scout

SERVICES = (chunker, inspector, scout)


class ConfigIdentityTests(unittest.TestCase):
    def test_every_config_is_named_for_the_identity_it_declares(self) -> None:
        for service in SERVICES:
            configs = service.available_configs()
            self.assertTrue(configs, f"{service.__name__} discovered no configs")
            for config in configs:
                with self.subTest(service=service.__name__, type_key=config.type_key):
                    self.assertEqual(
                        config.type_key,
                        f"{config.org}_{config.source_type}_{config.intervention_class}",
                        "type_key must spell out the triple it is filed under",
                    )

    def test_every_discovered_type_loads_back_by_its_own_identity(self) -> None:
        """The round trip is the real check: enumerate, then resolve what you got.

        `find_config` raises when a file's declared identity disagrees with the
        name it was resolved by, so a successful round trip proves the two agree
        without this test needing to know how paths are built.
        """
        for service in SERVICES:
            for config in service.available_configs():
                with self.subTest(service=service.__name__, type_key=config.type_key):
                    found = service.find_config(
                        config.org, config.source_type, config.intervention_class
                    )
                    self.assertEqual(found.type_key, config.type_key)

    def test_scaffolds_are_not_document_types(self) -> None:
        for service in SERVICES:
            keys = [config.type_key.upper() for config in service.available_configs()]
            with self.subTest(service=service.__name__):
                self.assertFalse([key for key in keys if "TEMPLATE" in key])
                self.assertFalse([key for key in keys if "EXAMPLE" in key])

    def test_the_document_tools_cover_the_same_triples(self) -> None:
        """A triple a grading tool claims must be one the chunker can parse.

        Coverage may legitimately be narrower - an Inspector rubric is optional,
        and the API probes for it. What must not differ is the *spelling* of a
        shared triple, which is what an unnoticed rename produces.
        """
        parseable = {config.type_key for config in chunker.available_configs()}
        for service in (inspector, scout):
            with self.subTest(service=service.__name__):
                unknown = sorted(
                    {config.type_key for config in service.available_configs()} - parseable
                )
                self.assertEqual(
                    unknown,
                    [],
                    f"{service.__name__} configures triples the chunker cannot parse",
                )

    def test_optional_rubrics_are_asked_about_rather_than_assumed(self) -> None:
        for config in chunker.available_configs():
            triple = (config.org, config.source_type, config.intervention_class)
            with self.subTest(type_key=config.type_key):
                if inspector.has_config(*triple):
                    inspector.find_config(*triple)


if __name__ == "__main__":
    unittest.main()
