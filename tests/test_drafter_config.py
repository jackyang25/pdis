"""Drafter's configuration: which sources to read and how to plan their searches."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from services import drafter
from services.drafter.configuration import load_config

VALID = """\
type_key: bmgf_itpp_vaccine
org: bmgf
source_type: itpp
intervention_class: vaccine
display_name: "BMGF Intervention TPP - Vaccine"
sources: [pubmed, who_guidelines]
query_guidance: Search for what comparable vaccines achieved.
programme_context: Products for low- and middle-income countries.
"""

def write(text: str) -> str:
    directory = Path(tempfile.mkdtemp())
    path = directory / "bmgf_itpp_vaccine.yaml"
    path.write_text(textwrap.dedent(text))
    return str(path)


class ShippedConfigTests(unittest.TestCase):
    def test_every_shipped_config_is_an_itpp_with_a_variable_list(self):
        configs = drafter.available_configs()
        self.assertEqual(
            {config.intervention_class for config in configs},
            {"vaccine", "drug", "diagnostic", "device"},
        )
        for config in configs:
            self.assertEqual(config.source_type, "itpp")
            self.assertTrue(config.sources)
            # Every draft says who it is for; a product type that did not would draft for
            # wherever its comparators happen to be licensed.
            self.assertTrue(config.programme_context.strip(), config.type_key)

    def test_an_unknown_triple_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            drafter.find_config("bmgf", "ctpp", "vaccine")


class ValidationTests(unittest.TestCase):
    def test_an_unregistered_source_is_refused(self):
        with self.assertRaises(ValueError):
            load_config(write(VALID.replace("[pubmed, who_guidelines]", "[pubmed, nowhere]")))

    def test_a_config_must_say_who_its_drafts_are_for(self):
        with self.assertRaisesRegex(ValueError, "programme_context"):
            load_config(write(VALID.replace("programme_context: Products for low- and middle-income countries.\n", "")))

    def test_a_source_that_returns_snippets_is_refused(self):
        with self.assertRaisesRegex(ValueError, "web"):
            load_config(write(VALID.replace("[pubmed, who_guidelines]", "[pubmed, web]")))

    def test_a_malformed_config_breaks_the_listing_rather_than_vanishing_from_it(self):
        directory = Path(write(VALID)).parent
        (directory / "bmgf_itpp_drug.yaml").write_text("org: bmgf\n")
        with mock.patch("services.drafter.configuration.CONFIGS_DIR", directory), self.assertRaises(ValueError):
            drafter.available_configs()

    def test_a_config_is_found_by_what_it_declares_not_by_its_filename(self):
        directory = Path(tempfile.mkdtemp())
        (directory / "vaccine_profile.yaml").write_text(VALID.replace("type_key: bmgf_itpp_vaccine", "type_key: vaccine_profile"))
        with mock.patch("services.drafter.configuration.CONFIGS_DIR", directory):
            self.assertEqual(drafter.find_config("bmgf", "itpp", "vaccine").type_key, "vaccine_profile")
            with self.assertRaises(LookupError):
                drafter.find_config("bmgf", "itpp", "drug")


if __name__ == "__main__":
    unittest.main()
