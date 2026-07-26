from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.scout.contract import validate_result_contract
from services.scout.models import (
    Attribute,
    DocumentContextValidation,
    DocumentSpan,
    FunnelStats,
    QUANTITATIVE_SEMANTIC_FIELDS,
    ScoutResult,
)
from services.scout.stages.conformity import (
    assemble_quantitative_document_ledger,
    empty_conformity_scores,
    extract_quantitative_ledger_batch,
    finalize_quantitative_document_review,
    prepare_quantitative_ledger_batches,
)


BLOCK_ID = "document/b-0001"


def _block() -> ContentBlock:
    return ContentBlock(
        id=BLOCK_ID,
        doc_id="document",
        ordinal=1,
        block_type="table",
        content=(
            "Variable: Formulation, Dosage and Route of Administration\n"
            "Optimal:\n"
            "Dose volume: <0.5 mL/dose for pediatric; <1.0 mL/dose for adult.\n"
            "Threshold:\n"
            "Dose volume: <1.0 mL/dose for pediatric and adult."
        ),
        heading_stack=[],
        structural_meta={},
        style_hint={},
    )


def _profile(population: str) -> dict:
    profile = {
        field_name: {
            "state": "not_specified",
            "value": "",
            "other": "",
            "source_refs": [],
        }
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS
    }
    profile["measure"] = {
        "state": "specified",
        "value": "Dose volume",
        "other": "",
        "source_refs": ["statement"],
    }
    profile["population"] = {
        "state": "specified",
        "value": population,
        "other": "",
        "source_refs": ["statement"],
    }
    return profile


def _target(quote: str, value: float, role: str, population: str) -> dict:
    profile = _profile(population)
    provenance = {field_name: [] for field_name in QUANTITATIVE_SEMANTIC_FIELDS}
    for field_name in ("measure", "population"):
        provenance[field_name] = [{"quote": quote, "block_ids": [BLOCK_ID]}]
    return {
        "attribute_ref": "vaccine.dose_volume",
        "quote": quote,
        "expression": {
            "kind": "bound",
            "unit": "mL/dose",
            "value": value,
            "lower": None,
            "upper": None,
            "comparator": "<",
        },
        "role": role,
        "comparison_dimensions": ["measure", "population"],
        "semantic_profile": profile,
        "semantic_provenance": provenance,
        "provenance_spans": [{"quote": quote, "block_ids": [BLOCK_ID]}],
        "ownership_reason": "Dose volume directly owns the measured quantity.",
    }


class _LedgerClient:
    def __init__(self, reviews: list[dict]):
        self.reviews = reviews
        self.calls = 0
        self.system_prompt = ""
        self.user_message = ""

    def call_structured(self, system_prompt, user_message, *_args, **_kwargs):
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_message = user_message
        return {"reviews": self.reviews}


class _SequenceLedgerClient:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.calls = 0
        self.schemas: list[dict] = []

    def call_structured(self, *_args, schema, **_kwargs):
        self.schemas.append(schema)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return {"reviews": response}


class QuantitativeDocumentLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.attributes = [
            Attribute(
                name="vaccine.product",
                description="Broad product identity and formulation",
                block_ids=[BLOCK_ID],
                document_target=_block().content,
                document_spans=[
                    DocumentSpan(quote=_block().content, block_ids=[BLOCK_ID])
                ],
                target_resolved=True,
                target_resolution_reason="Resolved from exact document spans.",
            ),
            Attribute(
                name="vaccine.dose_volume",
                description="Volume administered per dose",
                document_spans=[
                    DocumentSpan(quote=_block().content, block_ids=[BLOCK_ID])
                ],
                target_resolved=True,
                target_resolution_reason="Resolved from exact document spans.",
            ),
        ]
        self.batches = prepare_quantitative_ledger_batches([_block()])
        self.assertEqual(len(self.batches), 1)

    def test_dense_source_block_is_split_into_bounded_unit_batches(self) -> None:
        source = ContentBlock(
            id="document/b-dense",
            doc_id="document",
            ordinal=2,
            block_type="table_row",
            content="\n".join(f"Constraint {index}: {index} units" for index in range(50)),
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )

        batches = prepare_quantitative_ledger_batches([source], max_units=10)
        unit_ids = [unit.id for batch in batches for unit in batch.units]

        self.assertEqual(len(batches), 5)
        self.assertTrue(all(len(batch.units) <= 10 for batch in batches))
        self.assertEqual(len(unit_ids), len(set(unit_ids)))
        self.assertTrue(all(batch.blocks == [source] for batch in batches))

    def test_production_batches_preserve_canonical_spans_and_fixed_ownership(self) -> None:
        full_span = "Optimal: Dose volume <0.5 mL/dose; adult use only."
        attribute = Attribute(
            name="vaccine.dose_volume",
            description="Volume administered per dose",
            document_spans=[DocumentSpan(quote=full_span, block_ids=[BLOCK_ID])],
            target_resolved=True,
            target_resolution_reason="Resolved from an exact field span.",
        )

        batches = prepare_quantitative_ledger_batches([_block()], [attribute])
        units = [unit for batch in batches for unit in batch.units]

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].quote, full_span)
        self.assertEqual(units[0].attribute_ref, attribute.name)

    def test_document_target_review_is_required_and_rejections_do_not_project(self) -> None:
        unit = next(item for item in self.batches[0].units if "<0.5" in item.quote)
        client = _LedgerClient([
            (
                {
                    "unit_id": other.id,
                    "classification": "target",
                    "attribute_ref": "vaccine.dose_volume",
                    "reason": "The statement sets a dose-volume target.",
                    "targets": [_target(other.quote, 0.5, "optimal", "pediatric")],
                }
                if other.id == unit.id
                else {
                    "unit_id": other.id,
                    "classification": "non_numeric",
                    "attribute_ref": "",
                    "reason": "No scalar target.",
                    "targets": [],
                }
            )
            for other in self.batches[0].units
        ])
        result = extract_quantitative_ledger_batch(
            self.batches[0],
            self.attributes,
            client,
            indication="malaria",
            intervention_class="vaccine",
        )
        projected, ledger = assemble_quantitative_document_ledger(
            self.attributes,
            self.batches,
            [result],
        )
        with self.assertRaisesRegex(ValueError, "review is incomplete"):
            finalize_quantitative_document_review(projected, ledger)

        for target in ledger.targets:
            target.review_status = "rejected"
        finalized, _ = finalize_quantitative_document_review(projected, ledger)
        self.assertTrue(all(not attribute.quantitative_targets for attribute in finalized))

    def test_numeric_batch_inherits_cross_field_canonical_context_with_exact_provenance(
        self,
    ) -> None:
        numeric_block = ContentBlock(
            id="document/b-0005",
            doc_id="document",
            ordinal=5,
            block_type="paragraph",
            content="Target protective efficacy is >80%.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        population_block = ContentBlock(
            id="document/b-0002",
            doc_id="document",
            ordinal=2,
            block_type="paragraph",
            content="Target population: children aged 5-17 months.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        efficacy = Attribute(
            name="vaccine.efficacy",
            description="Protective efficacy",
            document_spans=[
                DocumentSpan(quote=numeric_block.content, block_ids=[numeric_block.id])
            ],
            target_resolved=True,
        )
        population = Attribute(
            name="vaccine.target_population",
            description="Intended population",
            document_spans=[
                DocumentSpan(
                    quote=population_block.content,
                    block_ids=[population_block.id],
                )
            ],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([numeric_block])[0]
        unit = batch.units[0]
        profile = {
            field_name: {
                "state": "not_specified",
                "value": "",
                "other": "",
                "source_refs": [],
            }
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
        profile["measure"] = {
            "state": "specified",
            "value": "protective efficacy",
            "other": "",
            "source_refs": ["statement"],
        }
        profile["population"] = {
            "state": "specified",
            "value": "children aged 5-17 months",
            "other": "",
            "source_refs": ["binding-0002"],
        }
        client = _LedgerClient([
            {
                "unit_id": unit.id,
                "classification": "target",
                "attribute_ref": efficacy.name,
                "reason": "The statement sets the efficacy target.",
                "targets": [
                    {
                        "attribute_ref": efficacy.name,
                        "quote": numeric_block.content,
                        "expression": {
                            "kind": "bound",
                            "unit": "%",
                            "value": 80,
                            "lower": None,
                            "upper": None,
                            "comparator": ">",
                        },
                        "role": "threshold",
                        "comparison_dimensions": ["measure", "population"],
                        "semantic_profile": profile,
                        "ownership_reason": "The local statement is an efficacy target.",
                    }
                ],
            }
        ])

        result = extract_quantitative_ledger_batch(
            batch,
            [efficacy, population],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(len(result.targets), 1)
        target = result.targets[0]
        self.assertEqual(
            target.semantic_provenance["measure"][0].block_ids,
            [numeric_block.id],
        )
        self.assertEqual(
            target.semantic_provenance["population"][0].block_ids,
            [population_block.id],
        )
        self.assertIn(population_block.content, client.system_prompt)
        self.assertNotIn(population_block.content, client.user_message)

    def test_long_field_span_uses_atomic_target_quote_as_provenance(self) -> None:
        atomic_quote = "Target efficacy >80% at 12 months."
        long_content = atomic_quote + " " + ("Supporting context without a new target. " * 30)
        self.assertGreater(len(long_content), 800)
        block = ContentBlock(
            id="document/b-0010",
            doc_id="document",
            ordinal=10,
            block_type="paragraph",
            content=long_content,
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="vaccine.efficacy",
            description="Protective efficacy",
            document_spans=[DocumentSpan(quote=long_content, block_ids=[block.id])],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([block], [attribute])[0]
        unit = batch.units[0]
        profile = {
            field_name: {
                "state": "not_specified",
                "value": "",
                "other": "",
                "source_refs": [],
            }
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
        profile["measure"] = {
            "state": "specified",
            "value": "protective efficacy",
            "other": "",
            "source_refs": ["statement"],
        }
        client = _LedgerClient([
            {
                "unit_id": unit.id,
                "classification": "target",
                "attribute_ref": attribute.name,
                "reason": "The statement sets an efficacy target.",
                "targets": [{
                    "attribute_ref": attribute.name,
                    "quote": atomic_quote,
                    "expression": {
                        "kind": "bound",
                        "unit": "%",
                        "value": 80,
                        "lower": None,
                        "upper": None,
                        "comparator": ">",
                    },
                    "role": "optimal",
                    "comparison_dimensions": ["measure"],
                    "semantic_profile": profile,
                    "ownership_reason": "The exact excerpt states the target.",
                }],
            }
        ])

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(len(result.targets), 1)
        self.assertEqual(result.targets[0].quote, atomic_quote)
        self.assertEqual(result.targets[0].doc_block_ids, [block.id])
        self.assertEqual(result.reviews[0].classification, "target")

    def test_one_document_ledger_captures_atomic_targets_without_field_competition(self) -> None:
        units = {unit.quote: unit for unit in self.batches[0].units}
        reviews = []
        for unit in self.batches[0].units:
            if unit.quote == "Dose volume: <0.5 mL/dose for pediatric":
                targets = [_target(unit.quote, 0.5, "optimal", "pediatric")]
                classification = "target"
            elif unit.quote == "<1.0 mL/dose for adult.":
                targets = [_target(unit.quote, 1.0, "optimal", "adult")]
                classification = "target"
            elif unit.quote == "Dose volume: <1.0 mL/dose for pediatric and adult.":
                targets = [
                    _target(unit.quote, 1.0, "threshold", population)
                    for population in ("pediatric", "adult")
                ]
                classification = "target"
            else:
                targets = []
                classification = "non_numeric"
            reviews.append(
                {
                    "unit_id": unit.id,
                    "classification": classification,
                    "attribute_ref": "",
                    "reason": "Complete statement classification.",
                    "targets": targets,
                }
            )

        client = _LedgerClient(reviews)
        batch_result = extract_quantitative_ledger_batch(
            self.batches[0],
            self.attributes,
            client,
            indication="malaria",
            intervention_class="vaccine",
        )
        attributes, ledger = assemble_quantitative_document_ledger(
            self.attributes, self.batches, [batch_result]
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(ledger.status, "complete")
        self.assertEqual(len(ledger.reviews), len(units))
        self.assertEqual(len(ledger.targets), 4)
        self.assertEqual(attributes[0].quantitative_targets, [])
        self.assertEqual(len(attributes[1].quantitative_targets), 4)
        self.assertEqual(attributes[1].block_ids, [BLOCK_ID])
        self.assertIn("<0.5 mL/dose", attributes[1].document_target)
        self.assertEqual(
            {(target.role, target.semantic_profile["population"].value)
             for target in attributes[1].quantitative_targets},
            {
                ("optimal", "pediatric"),
                ("optimal", "adult"),
                ("threshold", "pediatric"),
                ("threshold", "adult"),
            },
        )
        result = ScoutResult(
            matches=[],
            assessments=[],
            stats=FunnelStats(0, 0, 0, 0, 0, 0),
            context_validation=DocumentContextValidation(
                status="match",
                configured_indication="malaria",
                document_indication="malaria",
            ),
            quantitative_ledger=ledger,
            variables=attributes,
            blocks=[_block()],
            phase="target_review",
        )
        self.assertIs(validate_result_contract(result), result)

    def test_a_missing_statement_review_is_explicitly_uncertain(self) -> None:
        reviews = [
            {
                "unit_id": unit.id,
                "classification": "non_numeric",
                "attribute_ref": "",
                "reason": "No scalar target.",
                "targets": [],
            }
            for unit in self.batches[0].units[:-1]
        ]
        client = _LedgerClient(reviews)
        batch_result = extract_quantitative_ledger_batch(
            self.batches[0],
            self.attributes,
            client,
            indication="malaria",
            intervention_class="vaccine",
        )
        attributes, ledger = assemble_quantitative_document_ledger(
            self.attributes, self.batches, [batch_result]
        )

        self.assertEqual(ledger.status, "uncertain")
        self.assertEqual(client.calls, 2)
        self.assertEqual(ledger.reviews[-1].classification, "uncertain")
        self.assertTrue(all(
            attribute.quantitative_target_status == "not_applicable"
            for attribute in attributes
        ))

    def test_missing_statement_review_is_recovered_once(self) -> None:
        source = ContentBlock(
            id="document/b-0005",
            doc_id="document",
            ordinal=5,
            block_type="paragraph",
            content=(
                "Development work remains active.\n"
                "Phase 4 follow-up is planned."
            ),
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="drug.timeline",
            description="Development timeline",
            document_spans=[
                DocumentSpan(quote=source.content, block_ids=[source.id])
            ],
            target_resolved=True,
            target_resolution_reason="Resolved from exact document spans.",
        )
        batch = prepare_quantitative_ledger_batches([source])[0]
        first_unit, unit = batch.units
        retained = {
            "unit_id": first_unit.id,
            "classification": "non_numeric",
            "attribute_ref": "",
            "reason": "The statement contains no numeric content.",
            "targets": [],
        }
        recovered = {
            "unit_id": unit.id,
            "classification": "non_scalar",
            "attribute_ref": attribute.name,
            "reason": "The phase is a development category, not a scalar target.",
            "targets": [],
        }
        client = _SequenceLedgerClient([[retained], [recovered]])

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            client,
            indication="example condition",
            intervention_class="drug",
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(
            [review.classification for review in result.reviews],
            ["non_numeric", "non_scalar"],
        )
        first_ids = (
            client.schemas[0]["properties"]["reviews"]["items"]["properties"]
            ["unit_id"]["enum"]
        )
        retry_ids = (
            client.schemas[1]["properties"]["reviews"]["items"]["properties"]
            ["unit_id"]["enum"]
        )
        self.assertEqual(first_ids, [first_unit.id, unit.id])
        self.assertEqual(retry_ids, [unit.id])

    def test_context_and_numeric_categories_are_retained_without_calibration(self) -> None:
        source = ContentBlock(
            id="document/b-0002",
            doc_id="document",
            ordinal=2,
            block_type="paragraph",
            content=(
                "Tested under Zone IVb at 75% relative humidity.\n"
                "Phase 4 follow-up is described qualitatively."
            ),
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="drug.stability",
            description="Stability conditions and development stage",
            block_ids=[source.id],
            document_target=source.content,
            target_resolved=True,
        )
        batches = prepare_quantitative_ledger_batches([source])
        classifications = {
            "Tested under Zone IVb at 75% relative humidity.": "context_only",
            "Phase 4 follow-up is described qualitatively.": "non_scalar",
        }
        reviews = [
            {
                "unit_id": unit.id,
                "classification": classifications[unit.quote],
                "attribute_ref": attribute.name,
                "reason": "The statement is numeric context, not a scalar target.",
                "targets": [],
            }
            for unit in batches[0].units
        ]

        result = extract_quantitative_ledger_batch(
            batches[0],
            [attribute],
            _LedgerClient(reviews),
            indication="example condition",
            intervention_class="drug",
        )
        attributes, ledger = assemble_quantitative_document_ledger(
            [attribute], batches, [result]
        )

        self.assertEqual(ledger.status, "complete")
        self.assertEqual(attributes[0].quantitative_target_status, "not_applicable")
        self.assertEqual(
            {item.disposition for item in attributes[0].quantitative_statement_dispositions},
            {"context_only", "non_scalar"},
        )

    def test_context_from_an_unowned_block_stays_only_in_document_ledger(self) -> None:
        claim_block = ContentBlock(
            id="document/b-0010",
            doc_id="document",
            ordinal=10,
            block_type="paragraph",
            content="Indication: prevention of clinical malaria.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        context_block = ContentBlock(
            id="document/b-0030",
            doc_id="document",
            ordinal=30,
            block_type="paragraph",
            content="Phase 4 follow-up is planned.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="vaccine.indication",
            description="Disease or condition the vaccine addresses",
            document_spans=[
                DocumentSpan(
                    quote=claim_block.content,
                    block_ids=[claim_block.id],
                )
            ],
            target_resolved=True,
        )
        batches = prepare_quantitative_ledger_batches([context_block])
        unit = batches[0].units[0]
        batch_result = extract_quantitative_ledger_batch(
            batches[0],
            [attribute],
            _LedgerClient([
                {
                    "unit_id": unit.id,
                    "classification": "non_scalar",
                    "attribute_ref": attribute.name,
                    "reason": "This is development context, not a scalar target.",
                    "targets": [],
                }
            ]),
            indication="malaria",
            intervention_class="vaccine",
        )

        attributes, ledger = assemble_quantitative_document_ledger(
            [attribute], batches, [batch_result]
        )

        self.assertEqual(ledger.reviews[0].attribute_ref, attribute.name)
        self.assertEqual(attributes[0].quantitative_statement_dispositions, [])
        self.assertEqual(attributes[0].block_ids, [claim_block.id])
        self.assertEqual(attributes[0].quantitative_target_status, "not_applicable")

    def test_unowned_semantic_uncertainty_does_not_block_other_fields(self) -> None:
        claim_block = ContentBlock(
            id="document/b-0010",
            doc_id="document",
            ordinal=10,
            block_type="paragraph",
            content="Dose must be below 5 mg.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        background = ContentBlock(
            id="document/b-0030",
            doc_id="document",
            ordinal=30,
            block_type="paragraph",
            content="The global strategy targets elimination by 2040.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="drug.dose",
            description="Dose",
            document_spans=[
                DocumentSpan(quote=claim_block.content, block_ids=[claim_block.id])
            ],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([background])[0]
        unit = batch.units[0]
        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            _LedgerClient([
                {
                    "unit_id": unit.id,
                    "classification": "uncertain",
                    "attribute_ref": "",
                    "reason": "The date is background strategy context.",
                    "targets": [],
                }
            ]),
            indication="example condition",
            intervention_class="drug",
        )

        _, ledger = assemble_quantitative_document_ledger(
            [attribute], [batch], [result]
        )

        self.assertEqual(ledger.status, "complete")
        self.assertEqual(ledger.reviews[0].classification, "uncertain")


if __name__ == "__main__":
    unittest.main()
