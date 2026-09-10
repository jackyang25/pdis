"""Authored coverage and applicability are catalog policy, not engine branches."""
import unittest

from services.inspector.configuration import find_profile, resolve_profile
from services.chunker import ContentBlock
from services.inspector.pipeline import inspect_blocks_with_profile


class ICHCoverageTests(unittest.TestCase):
    def resolved(self, source_type, intervention="drug", facts=None):
        return resolve_profile(find_profile("bmgf", source_type, intervention), facts or {})

    def test_drug_profiles_include_maturity_specific_additions(self):
        expected = {
            "itpp": {"ich-q8-itpp"},
            "ctpp": {"ich-e9-ctpp", "ich-e10-ctpp", "ich-q8-ctpp"},
            "ipdp": {"ich-e8-ipdp", "ich-e9-ipdp", "ich-e10-ipdp", "ich-q8-ipdp",
                     "ich-q9-ipdp", "ich-m3-ipdp"},
        }
        for source_type, additions in expected.items():
            with self.subTest(source_type=source_type):
                self.assertLessEqual(additions, {r.rubric_id for r in self.resolved(source_type)})

    def test_m3_requires_explicit_small_molecule_fact(self):
        for value, status in [(None, "needs_context"), ("unknown", "needs_context"),
                              ("no", "outside_review_scope"), ("yes", "included")]:
            with self.subTest(value=value):
                facts = {} if value is None else {"small_molecule": value}
                review = next(r for r in self.resolved("ipdp", facts=facts)
                              if r.rubric_id == "ich-m3-ipdp")
                self.assertEqual(review.status, status)

    def test_clinical_guidance_is_shared_but_quality_scope_is_explicit(self):
        for intervention in ("vaccine", "monoclonal_antibody"):
            ids = {r.rubric_id for r in self.resolved("ctpp", intervention)}
            self.assertLessEqual({"ich-e9-ctpp", "ich-e10-ctpp"}, ids)
            self.assertNotIn("ich-q8-ctpp", ids)
        ids = {r.rubric_id for r in self.resolved("ipdp", "vaccine")}
        self.assertLessEqual({"ich-e8-ipdp", "ich-e9-ipdp", "ich-e10-ipdp", "ich-q9-ipdp"}, ids)
        self.assertNotIn("ich-m3-ipdp", ids)

    def test_devices_and_diagnostics_do_not_gain_medicinal_product_guidance(self):
        for intervention, types in [("device", ("itpp", "ctpp")),
                                     ("diagnostic", ("itpp", "ctpp", "ipdp"))]:
            for source_type in types:
                self.assertEqual([r.rubric_id for r in self.resolved(source_type, intervention)], ["bmgf"])

    def test_new_units_keep_common_shape_and_citable_source_sections(self):
        seen = set()
        facts = {"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"}
        for source_type in ("itpp", "ctpp", "ipdp"):
            for resolution in self.resolved(source_type, facts=facts):
                if not resolution.rubric_id.startswith(("ich-e8-", "ich-e9-", "ich-e10-", "ich-q8-", "ich-q9-", "ich-m3-")):
                    continue
                rubric = resolution.rubric
                seen.add(rubric.id)
                self.assertEqual(rubric.evidence_scope, "whole_document")
                self.assertIn("PDIS-authored", rubric.authority)
                sources = {source.id: source for source in rubric.sources}
                for section in rubric.config.sections:
                    for unit in section.variables or [section]:
                        self.assertTrue(unit.source_refs)
                        self.assertTrue(unit.expectations)
                        for ref in unit.source_refs:
                            self.assertTrue(sources[ref].url.startswith("https://database.ich.org/"))
                            self.assertTrue(sources[ref].revision)
        self.assertEqual(len(seen), 10)

    def test_expanded_reviews_run_and_retain_requirement_and_document_lineage(self):
        class Client:
            def call_structured(self, *_args, schema_name, schema, **_kwargs):
                if schema_name == "inspector_cross_section_consistency":
                    return {"findings": []}
                return {"verdict": "specified", "statement": "",
                        "block_ids": [schema["properties"]["block_ids"]["items"]["enum"][0]]}

        block = ContentBlock(id="plan:1", doc_id="plan", ordinal=1,
                             block_type="paragraph", content="Development evidence.",
                             heading_stack=[], structural_meta={}, style_hint={},
                             section_label="Other")
        facts = {"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"}
        for source_type, expected in [("itpp", 3), ("ctpp", 6), ("ipdp", 10)]:
            with self.subTest(source_type=source_type):
                result = inspect_blocks_with_profile(
                    [block], profile=find_profile("bmgf", source_type, "drug"),
                    applicability_facts=facts, llm_client=Client(),
                )
                # The pipeline validates the aggregate contract before returning.
                self.assertEqual(len(result.reviews), expected)
                for review in result.reviews[1:]:
                    requirements = {unit.id: unit for unit in review.rubric.requirements}
                    units = [unit for section in review.sections for unit in section.units]
                    self.assertEqual(set(requirements), {unit.id for unit in units})
                    for unit in units:
                        self.assertEqual(unit.cited_block_ids, [block.id])
                        self.assertTrue(requirements[unit.id].source_refs)
