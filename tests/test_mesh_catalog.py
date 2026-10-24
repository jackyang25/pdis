"""Terminology citations are checked offline, never inferred by a runtime search."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.vocabulary import indication_definitions, search_term


class CatalogTests(unittest.TestCase):
    def test_female_contraception_uses_its_specific_mesh_concept(self):
        from shared.vocabulary import intervention_classes

        for intervention_class in intervention_classes():
            with self.subTest(intervention_class=intervention_class):
                entries = {entry.key: entry for entry in indication_definitions(intervention_class)}
                self.assertIn("female_contraception", entries)
                entry = entries["female_contraception"]
                self.assertEqual(entry.mesh_descriptor, "D003267")
                self.assertEqual(entry.mesh_concept, "M0005088")
                self.assertEqual(entry.mesh_term, "Female Contraception")
                self.assertEqual(entry.match, "exact")
                self.assertEqual(search_term(entry.key), "female contraception")

    def test_citation_metadata_is_not_a_synonym_expander(self):
        # A key's search text is derived from the key alone; its MeSH citation never
        # becomes alternate runtime text.
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


class VocabularyFileTests(unittest.TestCase):
    def test_a_missing_vocabulary_file_is_an_error_not_an_empty_list(self):
        import shared.vocabulary as vocabulary

        missing = Path(tempfile.mkdtemp()) / "indications.yaml"
        with patch.object(vocabulary, "INDICATIONS_VOCAB", missing):
            with self.assertRaises(LookupError) as caught:
                vocabulary.indications_for("drug")
        self.assertNotIn(str(missing.parent), str(caught.exception))

    def test_each_file_is_read_once_per_process(self):
        import shared.vocabulary as vocabulary

        vocabulary.indications_for("drug")
        vocabulary.attribute_definitions("vaccine")
        with patch.object(vocabulary.yaml, "safe_load", side_effect=AssertionError("re-read")):
            vocabulary.indications_for("vaccine")
            vocabulary.intervention_classes()
            vocabulary.attribute_definitions("drug")
