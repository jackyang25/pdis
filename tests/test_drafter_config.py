"""Drafter's configuration: which sources to read and how to plan their searches."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

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

    def test_an_unknown_triple_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            drafter.find_config("bmgf", "ctpp", "vaccine")


class ValidationTests(unittest.TestCase):
    def test_an_unregistered_source_is_refused(self):
        with self.assertRaises(ValueError):
            load_config(write(VALID.replace("[pubmed, who_guidelines]", "[pubmed, nowhere]")))


if __name__ == "__main__":
    unittest.main()
