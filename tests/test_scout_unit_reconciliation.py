"""Dynamic units acquire identity before any retrieval references exist."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from services.scout.models import Attribute, DocumentSpan
from services.scout.stages.unit_extractor import extract_units


def unit(name, description, block_id="doc/b1"):
    return {
        "name": name, "description": description, "evidence_domain": "regulatory",
        "spans": [{"block_id": block_id, "start_line": 1, "end_line": 1}],
        "entities": [],
    }


def group(representative, *members):
    return {"representative_unit_id": representative, "member_unit_ids": list(members)}


class FixtureClient:
    def __init__(self, units, partitions):
        self.units = units
        self.partitions = iter(partitions)
        self.identity_inputs = []

    def call_structured(self, system, user, max_tokens, *, schema_name, **kwargs):
        if schema_name == "scout_unit_batch":
            return {"units": deepcopy(self.units)}
        if schema_name == "scout_unit_reconciliation":
            self.identity_inputs.append((json.loads(user), kwargs.get("images")))
            value = next(self.partitions)
            if isinstance(value, Exception):
                raise value
            return {"groups": deepcopy(value)}
        raise AssertionError(schema_name)


def extract(client, text="[block:doc/b1]\nProduct A submission is planned for 2030.", **kwargs):
    return extract_units(text, intervention_class="vaccine", source_type="ipdp",
                         indication="malaria", llm_client=client, **kwargs)


class UnitReconciliationTests(unittest.TestCase):
    def test_paraphrased_units_merge_before_returning_to_pipeline(self):
        client = FixtureClient([
            unit("submission_date", "Planned regulatory submission timing."),
            unit("filing_schedule", "Timing of the planned regulatory filing."),
        ], [[group("unit-1", "unit-0", "unit-1")]])
        result = extract(client)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "filing_schedule")
        self.assertEqual(result[0].document_target, "Product A submission is planned for 2030.")
        self.assertEqual(result[0].block_ids, ["doc/b1"])

    def test_shared_name_and_paragraph_do_not_force_distinct_claims_to_merge(self):
        client = FixtureClient([
            unit("timeline", "Timing of regulatory submission."),
            unit("timeline", "Timing of regulatory approval."),
        ], [[group("unit-0", "unit-0"), group("unit-1", "unit-1")]])
        result = extract(client, "[block:doc/b1]\nSubmission is planned in 2030; approval in 2031.")
        self.assertEqual([u.name for u in result], ["timeline", "timeline_2"])
        self.assertEqual([u.description for u in result], [
            "Timing of regulatory submission.", "Timing of regulatory approval.",
        ])

    def test_merge_preserves_every_passage_entity_and_input_object(self):
        from services.scout.models import EvidenceEntity
        from services.scout.stages.unit_reconciler import reconcile_units
        first = Attribute("filing", "Submission timing.", document_spans=[
            DocumentSpan("Product A filing is planned in 2030.", ["doc/b1"]),
        ], entities=[EvidenceEntity("Product A", "vaccine")],
            evidence_domain="regulatory", definition_mode="dynamic", target_resolved=True)
        second = Attribute("submission", "Submission timing.", document_spans=[
            DocumentSpan("Product A submission is planned for 2030.", ["doc/b2"]),
        ], evidence_domain="regulatory", definition_mode="dynamic", target_resolved=True)
        before = deepcopy([first, second])
        client = FixtureClient([], [[group("unit-1", "unit-1", "unit-0")]])
        result = reconcile_units([first, second], client)
        self.assertEqual([first, second], before)
        self.assertEqual(result[0].block_ids, ["doc/b1", "doc/b2"])
        self.assertEqual(result[0].document_target,
                         "Product A filing is planned in 2030. Product A submission is planned for 2030.")
        self.assertEqual(result[0].entities, first.entities)
        self.assertEqual(result[0].description, second.description)
        self.assertEqual(result[0].evidence_domain, "regulatory")

    def test_all_extraction_chunks_reach_one_identity_decision(self):
        first = "[block:doc/b1]\nSubmission is planned for 2030."
        second = "[block:doc/b2]\nFiling is planned for 2030."

        class ChunkClient(FixtureClient):
            def call_structured(self, system, user, max_tokens, *, schema_name, **kwargs):
                if schema_name == "scout_unit_batch":
                    block_id = "doc/b1" if "[block:doc/b1]" in user else "doc/b2"
                    return {"units": [unit("filing", "Planned submission timing.", block_id)]}
                return super().call_structured(system, user, max_tokens, schema_name=schema_name, **kwargs)

        client = ChunkClient([], [[group("unit-0", "unit-0", "unit-1")]])
        with patch("services.scout.stages.unit_extractor.UNIT_CONTEXT_CHARS", 60):
            result = extract(client, first + "\n\n" + second)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].block_ids, ["doc/b1", "doc/b2"])
        self.assertEqual(len(client.identity_inputs), 1)

    def test_invalid_partition_is_retried_then_stops_without_partial_results(self):
        invalid = [
            [], [group("unit-0", "unit-0")],
            [group("unit-0", "unit-0", "unit-0", "unit-1")],
            [group("unit-0", "unit-0", "unit-1"), group("unit-1", "unit-1")],
            [group("unit-0", "unit-1"), group("unit-1", "unit-0")],
            [group("unit-9", "unit-0", "unit-1")],
            [group("unit-0", "unit-0", "unit-1", "unit-9")],
            [group("unit-0"), group("unit-1", "unit-1")],
            [group("unit-0", "unit-0", "unit-1") | {"rewritten_claim": "Invented"}],
        ]
        for partition in invalid:
            with self.subTest(partition=partition):
                client = FixtureClient([unit("a", "A"), unit("b", "B")], [partition, partition])
                from shared.errors import ModelResponseError

                with self.assertRaisesRegex(ModelResponseError, "unit reconciliation"):
                    extract(client)
                self.assertEqual(len(client.identity_inputs), 2)

    def test_complete_retry_is_accepted(self):
        client = FixtureClient([unit("a", "A"), unit("b", "B")], [
            [], [group("unit-0", "unit-0"), group("unit-1", "unit-1")],
        ])
        self.assertEqual(len(extract(client)), 2)

    def test_provider_failure_is_not_reported_as_successful_deduplication(self):
        client = FixtureClient([unit("a", "A"), unit("b", "B")], [RuntimeError("provider failed")])
        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            extract(client)

    def test_zero_or_one_unit_needs_no_identity_call(self):
        client = FixtureClient([unit("a", "A")], [])
        self.assertEqual(len(extract(client)), 1)
        self.assertEqual(extract(client, ""), [])
        self.assertEqual(client.identity_inputs, [])

    def test_identity_receives_claim_scope_and_exactly_associated_visuals(self):
        client = FixtureClient([unit("a", "Submission timing."), unit("b", "Approval timing.")], [
            [group("unit-0", "unit-0"), group("unit-1", "unit-1")],
        ])
        extract(client, images_by_block_id={"doc/b1": "data:image/png;base64,AA==",
                                           "unused": "data:image/png;base64,BB=="})
        payload, images = client.identity_inputs[0]
        self.assertEqual(payload[0]["description"], "Submission timing.")
        self.assertEqual(payload[1]["description"], "Approval timing.")
        self.assertEqual(payload[0]["document_spans"], [
            {"quote": "Product A submission is planned for 2030.", "block_ids": ["doc/b1"]},
        ])
        self.assertEqual(images, [{"block_id": "doc/b1", "data_url": "data:image/png;base64,AA=="}])

    def test_model_group_order_does_not_reorder_document_units(self):
        client = FixtureClient([unit("a", "A"), unit("b", "B"), unit("c", "C")], [
            [group("unit-1", "unit-1"), group("unit-2", "unit-2", "unit-0")],
        ])
        self.assertEqual([u.name for u in extract(client)], ["c", "b"])

    def test_generated_names_never_collide_with_existing_suffixes(self):
        client = FixtureClient([unit("a", "A"), unit("a", "B"), unit("a_2", "C")], [
            [group("unit-0", "unit-0"), group("unit-1", "unit-1"), group("unit-2", "unit-2")],
        ])
        names = [u.name for u in extract(client)]
        self.assertEqual(len(set(names)), 3)

    def test_fixed_tpp_provider_does_not_enter_dynamic_reconciliation(self):
        from services.scout import find_config
        from services.scout.pipeline import _resolve_units
        config = find_config("bmgf", "itpp", "vaccine")
        with patch("services.scout.stages.unit_extractor.reconcile_units",
                   side_effect=AssertionError("Fixed fields must not be reconciled")):
            fields = _resolve_units(config, "", [], FixtureClient([], []), indication="malaria")
        self.assertTrue(fields)
        self.assertTrue(all(field.definition_mode == "fixed" for field in fields))


if __name__ == "__main__":
    unittest.main()
