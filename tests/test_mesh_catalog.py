"""Terminology citations are checked offline, never inferred by a runtime search."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.vocabulary import indication_definitions, is_known_indication, search_term


class CatalogTests(unittest.TestCase):
    def test_retired_keys_remain_readable_without_becoming_new_choices(self):
        entries = indication_definitions("drug")
        for entry in entries:
            for old in entry.legacy_keys:
                self.assertTrue(is_known_indication("drug", old))
                self.assertNotIn(old, [item.key for item in entries])
        self.assertFalse(is_known_indication("unsupported", "rsv"))
        self.assertFalse(is_known_indication("drug", "not_a_context"))
        # Citation/legacy metadata does not become a runtime synonym expander.
        self.assertEqual(search_term("rsv"), "rsv")
        self.assertEqual(search_term("respiratory_syncytial_virus"), "respiratory syncytial virus")

    def test_narrower_contexts_cannot_claim_an_exact_mesh_name(self):
        entries = {entry.key: entry for entry in indication_definitions("drug")}
        for key in ("acute_malnutrition", "childhood_stunting", "soil_transmitted_helminthiases"):
            self.assertEqual(entries[key].match, "narrower")
            self.assertTrue(entries[key].note)
        # A child concept matters: Nipah is not the whole Henipavirus descriptor.
        self.assertEqual(entries["nipah_virus_infection"].mesh_concept, "M000622434")
        self.assertEqual(entries["cervical_cancer"].mesh_concept, "M0003943")

    def test_malformed_or_colliding_entries_fail_before_discovery(self):
        good = {"key": "malaria", "mesh": {"descriptor": "D008288", "concept": "M0012910", "term": "Malaria"}, "match": "exact"}
        bad = [
            [good, good],
            [{**good, "legacy_keys": ["malaria"]}],
            [{**good, "match": "narrower"}],
            [{**good, "mesh": {**good["mesh"], "concept": "wrong"}}],
        ]
        for values in bad:
            with self.subTest(values=values), patch("shared.vocabulary._indications_document", return_value={"drug": values}):
                with self.assertRaises(ValueError):
                    indication_definitions("drug")


class MeshVerificationTests(unittest.TestCase):
    def test_checks_descriptor_concept_and_term_not_just_similar_text(self):
        from scripts.check_indication_mesh import verify_mesh
        from shared.vocabulary import IndicationDefinition
        xml = '''<DescriptorRecordSet><DescriptorRecord>
          <DescriptorUI>D008288</DescriptorUI><ConceptList><Concept>
          <ConceptUI>M0012910</ConceptUI><TermList><Term><String>Malaria</String></Term></TermList>
          </Concept></ConceptList></DescriptorRecord></DescriptorRecordSet>'''
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "desc2026.xml"
            source.write_text(xml)
            good = IndicationDefinition("malaria", "D008288", "M0012910", "Malaria", "exact")
            self.assertEqual(verify_mesh(source, (good,)), [])
            for bad in (
                IndicationDefinition("malaria", "D000001", "M0012910", "Malaria", "exact"),
                IndicationDefinition("malaria", "D008288", "M0000001", "Malaria", "exact"),
                IndicationDefinition("malaria", "D008288", "M0012910", "Similar malaria", "exact"),
                IndicationDefinition("severe_malaria", "D008288", "M0012910", "Malaria", "exact"),
            ):
                self.assertTrue(verify_mesh(source, (bad,)))
            narrower = IndicationDefinition("severe_malaria", "D008288", "M0012910", "Malaria", "narrower", note="Severe cases only.")
            self.assertEqual(verify_mesh(source, (narrower,)), [])
