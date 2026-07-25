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
        field_name: {"state": "not_specified", "value": "", "other": ""}
        for field_name in QUANTITATIVE_SEMANTIC_FIELDS
    }
    profile["measure"] = {
        "state": "specified",
        "value": "Dose volume",
        "other": "",
    }
    profile["population"] = {
        "state": "specified",
        "value": population,
        "other": "",
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

    def call_structured(self, *_args, **_kwargs):
        self.calls += 1
        return {"reviews": self.reviews}


class _SequenceLedgerClient:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.calls = 0

    def call_structured(self, *_args, **_kwargs):
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
            conformity=empty_conformity_scores(attributes),
            variables=attributes,
            blocks=[_block()],
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
            content="Phase 4 follow-up is planned.",
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
        unit = batch.units[0]
        recovered = {
            "unit_id": unit.id,
            "classification": "non_scalar",
            "attribute_ref": attribute.name,
            "reason": "The phase is a development category, not a scalar target.",
            "targets": [],
        }
        client = _SequenceLedgerClient([[], [recovered]])

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            client,
            indication="example condition",
            intervention_class="drug",
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(result.reviews[0].classification, "non_scalar")

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


if __name__ == "__main__":
    unittest.main()
