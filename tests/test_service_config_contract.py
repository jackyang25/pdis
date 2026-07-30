"""Config lookup presents the same contract as every other service's."""

from __future__ import annotations

import unittest

from services import chunker, inspector, scout


class ConfigLookupContractTests(unittest.TestCase):
    UNKNOWN = ("nosuchorg", "nosuchtype", "nosuchclass")

    def test_every_service_signals_a_missing_config_the_same_way(self) -> None:
        for module in (chunker, inspector, scout):
            with self.subTest(service=module.__name__):
                with self.assertRaises(LookupError):
                    module.find_config(*self.UNKNOWN)

    def test_optional_rubrics_are_asked_about_explicitly(self) -> None:
        """Inspector rubrics are optional, so callers get a predicate to ask."""
        self.assertFalse(inspector.has_config(*self.UNKNOWN))


if __name__ == "__main__":
    unittest.main()


class ConfigDiscoveryTests(unittest.TestCase):
    """Which document types exist is the chunker's fact, not the API's."""

    def test_the_chunker_enumerates_its_own_document_types(self) -> None:
        configs = chunker.available_configs()

        self.assertTrue(configs, "no chunker document types were discovered")
        for config in configs:
            with self.subTest(type_key=config.type_key):
                self.assertTrue(config.org)
                self.assertTrue(config.source_type)
                self.assertTrue(config.intervention_class)

    def test_template_scaffolds_are_not_document_types(self) -> None:
        keys = [config.type_key.upper() for config in chunker.available_configs()]

        self.assertFalse([key for key in keys if "TEMPLATE" in key])

    def test_every_discovered_type_can_be_loaded_by_its_identity(self) -> None:
        for config in chunker.available_configs():
            with self.subTest(type_key=config.type_key):
                found = chunker.find_config(
                    config.org, config.source_type, config.intervention_class
                )
                self.assertEqual(found.type_key, config.type_key)


class ResultContractShapeTests(unittest.TestCase):
    """Every service's result validator presents the same shape."""

    def test_each_validator_returns_the_result_it_validated(self) -> None:
        import inspect

        from services.aligner.contract import (
            validate_result_contract as validate_alignment,
        )
        from services.inspector.contract import (
            validate_result_contract as validate_inspection,
        )
        from services.scout.contract import (
            validate_result_contract as validate_scout,
        )

        for validator in (validate_alignment, validate_inspection, validate_scout):
            with self.subTest(validator=validator.__module__):
                annotation = inspect.signature(validator).return_annotation
                self.assertNotIn(
                    annotation,
                    (None, "None"),
                    "a validator that returns nothing cannot be composed inline",
                )

    def test_a_validator_takes_the_result_and_its_config_only(self) -> None:
        import inspect

        from services.inspector.contract import validate_result_contract

        parameters = list(inspect.signature(validate_result_contract).parameters)
        self.assertEqual(
            parameters,
            ["result", "config"],
            "blocks are already carried on the result; the extra parameter can drift",
        )
