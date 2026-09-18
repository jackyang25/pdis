"""Guideline scope is resolved before assessment, never inferred by the model."""
import unittest

from fastapi.testclient import TestClient

from services.inspector.configuration import find_profile, resolve_profile
from services.chunker import ContentBlock
from services.inspector.pipeline import inspect_blocks_with_profile
from services.inspector.models import inspection_result_to_dict


CASES = [
    ("itpp", "vaccine", "who-vaccine-presentation-itpp", "public_sector_vaccine"),
    ("ctpp", "vaccine", "who-vaccine-presentation-ctpp", "public_sector_vaccine"),
    ("ipdp", "vaccine", "ema-vaccine-clinical-ipdp", "infectious_disease_vaccine"),
    ("ipdp", "diagnostic", "who-tgs2-ipdp", "who_prequalification_ivd"),
    ("ipdp", "diagnostic", "who-tgs3-ipdp", "who_prequalification_ivd"),
    ("ctpp", "diagnostic", "fda-diagnostic-performance-ctpp", "binary_diagnostic_result"),
    ("ipdp", "diagnostic", "fda-diagnostic-performance-ipdp", "binary_diagnostic_result"),
    ("itpp", "device", "fda-human-factors-itpp", None),
    ("ctpp", "device", "fda-human-factors-ctpp", None),
]


class GuidelineCoverageTests(unittest.TestCase):
    def test_scope_is_explicit_and_unknown_never_becomes_included(self):
        for source_type, product, rubric_id, fact in CASES:
            for value, status in [(None, "needs_context"), ("unknown", "needs_context"),
                                  ("no", "outside_review_scope"), ("yes", "included")]:
                with self.subTest(rubric=rubric_id, value=value):
                    facts = {fact: value} if fact and value else {}
                    resolutions = resolve_profile(find_profile("bmgf", source_type, product), facts)
                    review = next((r for r in resolutions if r.rubric_id == rubric_id), None)
                    self.assertIsNotNone(review)
                    self.assertEqual(review.status, status if fact else "included")
                    self.assertEqual(review.required_facts,
                                     [fact] if fact and status == "needs_context" else [])

    def test_catalog_exposes_only_relevant_questions_through_existing_api(self):
        from api.main import app

        client = TestClient(app)
        expected = {
            ("itpp", "vaccine"): {"public_sector_vaccine"},
            ("ipdp", "vaccine"): {"infectious_disease_vaccine"},
            ("ctpp", "diagnostic"): {"binary_diagnostic_result"},
            ("ipdp", "diagnostic"): {"who_prequalification_ivd", "binary_diagnostic_result"},
            ("itpp", "device"): set(),
        }
        for (source_type, product), keys in expected.items():
            with self.subTest(source_type=source_type, product=product):
                response = client.get("/api/configs/inspector", params={
                    "org": "bmgf", "source_type": source_type, "intervention_class": product,
                })
                self.assertEqual(response.status_code, 200)
                fields = response.json()["applicability_facts"]
                self.assertEqual({f["key"] for f in fields}, keys)
                for field in fields:
                    self.assertEqual(field["options"], ["yes", "no", "unknown"])

    def test_new_authorities_do_not_leak_into_other_profiles(self):
        for product, types in [("drug", ("itpp", "ctpp", "ipdp")),
                               ("monoclonal_antibody", ("itpp", "ctpp")),
                               ("diagnostic", ("itpp",))]:
            for source_type in types:
                ids = [r.rubric_id for r in resolve_profile(find_profile("bmgf", source_type, product), {})]
                self.assertFalse(any(i.startswith(("who-", "fda-", "ema-")) for i in ids))

    def test_new_reviews_use_shared_pipeline_and_preserve_source_lineage(self):
        from api.schemas import InspectionResultOut

        class Client:
            def call_structured(self, *_args, schema_name, schema, **_kwargs):
                if schema_name == "inspector_cross_section_consistency":
                    return {"findings": []}
                return {"verdict": "specified", "statement": "",
                        "block_ids": [schema["properties"]["block_ids"]["items"]["enum"][0]]}

        block = ContentBlock(id="plan:1", doc_id="plan", ordinal=1,
                             block_type="paragraph", content="Product targets and planned studies.",
                             heading_stack=[], structural_meta={}, style_hint={}, section_label="Other")
        facts = {fact: "yes" for _, _, _, fact in CASES if fact}
        for source_type, product in sorted({(s, p) for s, p, _, _ in CASES}):
            result = inspect_blocks_with_profile(
                [block], profile=find_profile("bmgf", source_type, product),
                applicability_facts=facts, indication="malaria", llm_client=Client(),
            )
            expected = {r for s, p, r, _ in CASES if (s, p) == (source_type, product)}
            reviews = [r for r in result.reviews if r.rubric.id in expected]
            self.assertEqual({r.rubric.id for r in reviews}, expected)
            for review in reviews:
                self.assertIn("PDIS-authored", review.rubric.authority)
                sources = {s.id for s in review.rubric.sources}
                self.assertTrue(sources)
                for requirement in review.rubric.requirements:
                    self.assertTrue(requirement.source_refs)
                    self.assertLessEqual(set(requirement.source_refs), sources)
                for section in review.sections:
                    for unit in section.units:
                        self.assertEqual(unit.cited_block_ids, [block.id])
            exported = InspectionResultOut.model_validate(inspection_result_to_dict(result)).model_dump()
            self.assertEqual(exported["applicability_facts"], facts)
            self.assertEqual([b["id"] for b in exported["blocks"]], [block.id])
            for review in exported["reviews"]:
                if review["rubric"]["id"] in expected:
                    self.assertTrue(all(s["is_present"] is None for s in review["sections"]))
