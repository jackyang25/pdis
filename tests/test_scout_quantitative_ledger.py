from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.scout.contract import validate_result_contract
from services.scout.pipeline import _active_quantitative_targets
from services.scout.models import (
    Attribute,
    ComparisonRule,
    DocumentContextValidation,
    DocumentSpan,
    FunnelStats,
    NumericExpression,
    QUANTITATIVE_SEMANTIC_FIELDS,
    QuantitativeFieldLink,
    QuantitativeLedger,
    QuantitativeLedgerReview,
    QuantitativeTarget as _QuantitativeTarget,
    ScoutResult,
    SemanticSlot,
)
from services.scout.stages.conformity import (
    assemble_quantitative_document_ledger,
    empty_conformity_scores,
    extract_quantitative_ledger_batch,
    finalize_quantitative_document_review,
    prepare_quantitative_ledger_batches,
    reconcile_quantitative_document_ledger,
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


def _comparison_contract(
    profile: dict,
    dimensions: tuple[str, ...] = ("measure",),
) -> dict:
    contract = {}
    for field_name in QUANTITATIVE_SEMANTIC_FIELDS:
        slot = profile[field_name]
        scope = str(slot.get("value") or slot.get("other") or field_name)
        if field_name == "measure":
            contract[field_name] = {
                "mode": "exact",
                "scope": scope,
                "reason": "The measured quantity must match.",
            }
        elif field_name in dimensions:
            contract[field_name] = {
                "mode": "compatible",
                "scope": scope,
                "reason": "The fixture permits compatible values within this scope.",
            }
        else:
            contract[field_name] = {
                "mode": "unconstrained",
                "scope": "",
                "reason": "This dimension does not control fixture admission.",
            }
    return contract


def QuantitativeTarget(*args, **kwargs):
    """Keep compact model fixtures aligned with the current target contract."""
    if "comparison_contract" not in kwargs:
        profile = kwargs.get("semantic_profile") or {
            "measure": SemanticSlot(state="specified", value="numeric measure")
        }
        raw_profile = {
            field_name: {
                "state": getattr(profile.get(field_name), "state", "not_specified"),
                "value": getattr(profile.get(field_name), "value", ""),
                "other": getattr(profile.get(field_name), "other", ""),
            }
            for field_name in QUANTITATIVE_SEMANTIC_FIELDS
        }
        dimensions = tuple(
            field_name
            for field_name, slot in raw_profile.items()
            if slot["state"] in {"specified", "other", "unknown"}
        )
        kwargs["comparison_contract"] = _comparison_contract(
            raw_profile, dimensions
        )
    return _QuantitativeTarget(*args, **kwargs)


def _target(quote: str, value: float, role: str, population: str) -> dict:
    profile = _profile(population)
    provenance = {field_name: [] for field_name in QUANTITATIVE_SEMANTIC_FIELDS}
    for field_name in ("measure", "population"):
        provenance[field_name] = [{"quote": quote, "block_ids": [BLOCK_ID]}]
    return {
        "field_links": [{
            "attribute_ref": "vaccine.dose_volume",
            "relation": "defines",
            "reason": "The statement directly specifies dose volume.",
        }],
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
    }


def _current_review(review: dict) -> dict:
    """Migrate compact historical fixtures at the test-provider boundary."""
    attribute_ref = str(review.get("attribute_ref", ""))
    targets = []
    for target in review.get("targets", []):
        primary_ref = str(target.get("attribute_ref", attribute_ref))
        related_refs = target.get("related_attribute_refs", [])
        field_links = target.get("field_links") or [
            *([{
                "attribute_ref": primary_ref,
                "relation": "defines",
                "reason": "Test fixture links the claim to its product field.",
            }] if primary_ref else []),
            *[{
                "attribute_ref": value,
                "relation": "context_for",
                "reason": "Test fixture retains a related product view.",
            } for value in related_refs if value and value != primary_ref],
        ]
        current_target = {
            key: value
            for key, value in {**target, "field_links": field_links}.items()
            if key not in {
                "attribute_ref", "related_attribute_refs", "ownership_reason",
                "comparison_dimensions",
            }
        }
        profile = current_target.get("semantic_profile") or {}
        current_target["comparison_contract"] = target.get(
            "comparison_contract"
        ) or _comparison_contract(
            profile,
            tuple(target.get("comparison_dimensions") or ("measure",)),
        )
        targets.append(current_target)
    return {
        **review,
        "attribute_refs": review.get("attribute_refs")
        or ([attribute_ref] if attribute_ref else []),
        "targets": targets,
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
        return {"reviews": [_current_review(review) for review in self.reviews]}


class _SequenceLedgerClient:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.calls = 0
        self.schemas: list[dict] = []
        self.user_messages: list[str] = []

    def call_structured(self, _system_prompt, user_message, *_args, schema, **_kwargs):
        self.schemas.append(schema)
        self.user_messages.append(user_message)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return {"reviews": [_current_review(review) for review in response]}


class _ReconciliationClient:
    def __init__(self, groups: list[dict]):
        self.groups = groups
        self.calls = 0

    def call_structured(self, *_args, **_kwargs):
        self.calls += 1
        return {"groups": self.groups}


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

    def test_document_wide_reconciliation_merges_one_repeated_atomic_claim(self) -> None:
        field_names = (
            "vaccine.regimen_compliance",
            "vaccine.dosing_schedule",
            "vaccine.duration_of_protection",
        )
        attributes = [
            Attribute(
                name=name,
                description=name.replace("vaccine.", "").replace("_", " "),
                block_ids=[f"document/b-000{index}"],
                document_target="Booster no more frequent than annually.",
                document_spans=[
                    DocumentSpan(
                        quote="Booster no more frequent than annually.",
                        block_ids=[f"document/b-000{index}"],
                    )
                ],
                target_resolved=True,
            )
            for index, name in enumerate(field_names, start=1)
        ]

        def target(index: int, links: list[QuantitativeFieldLink]) -> QuantitativeTarget:
            quote = (
                "Booster no more frequent than annually."
                if index != 2
                else "At most one booster may be given per year."
            )
            block_id = f"document/b-000{index}"
            profile = {
                field_name: SemanticSlot()
                for field_name in QUANTITATIVE_SEMANTIC_FIELDS
            }
            profile["measure"] = SemanticSlot(
                state="specified",
                value="booster frequency",
            )
            span = DocumentSpan(quote=quote, block_ids=[block_id])
            return QuantitativeTarget(
                id=f"qt-{index}",
                expression=NumericExpression(
                    kind="bound",
                    unit="boosters/year",
                    value=1,
                    comparator="<=",
                ),
                role="threshold",
                quote=quote,
                doc_block_ids=[block_id],
                field_links=links,
                semantic_profile=profile,
                comparison_contract={
                    field_name: ComparisonRule(
                        mode="exact" if field_name == "measure" else "unconstrained",
                        scope="booster frequency" if field_name == "measure" else "",
                        reason="Fixture comparison rule.",
                    )
                    for field_name in QUANTITATIVE_SEMANTIC_FIELDS
                },
                semantic_provenance={"measure": [span]},
                provenance_spans=[span],
                review_status="needs_review",
            )

        targets = [
            target(1, [
                QuantitativeFieldLink(
                    field_names[0], "defines", "Direct regimen limit."
                ),
                QuantitativeFieldLink(
                    field_names[1], "constrains", "Constrains dosing."
                ),
            ]),
            target(2, [
                QuantitativeFieldLink(
                    field_names[2], "defines", "Direct duration limit."
                ),
                QuantitativeFieldLink(
                    field_names[1], "constrains", "Constrains dosing."
                ),
            ]),
            target(3, [
                QuantitativeFieldLink(
                    field_names[1], "defines", "Direct dosing limit."
                )
            ]),
        ]
        ledger = QuantitativeLedger(
            status="complete",
            reason="Three source-verifiable proposals.",
            block_ids=[
                block_id
                for target_value in targets
                for block_id in target_value.doc_block_ids
            ],
            reviews=[
                QuantitativeLedgerReview(
                    unit_id=f"unit-{index}",
                    block_id=target_value.doc_block_ids[0],
                    quote=target_value.quote,
                    classification="target",
                    reason="Numeric document target.",
                    attribute_refs=target_value.analysis_attribute_refs,
                    target_ids=[target_value.id],
                )
                for index, target_value in enumerate(targets, start=1)
            ],
            targets=targets,
        )
        client = _ReconciliationClient([{
            "representative_target_id": "qt-3",
            "member_target_ids": ["qt-1", "qt-2", "qt-3"],
            "reason": "The passages repeat the same annual booster limit.",
        }])

        projected, reconciled = reconcile_quantitative_document_ledger(
            attributes,
            ledger,
            client,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual([item.id for item in reconciled.targets], ["qt-3"])
        self.assertEqual(
            set(reconciled.targets[0].doc_block_ids),
            {"document/b-0001", "document/b-0002", "document/b-0003"},
        )
        self.assertEqual(
            {
                (link.attribute_ref, link.relation)
                for link in reconciled.targets[0].field_links
            },
            {
                (field_names[0], "defines"),
                (field_names[1], "defines"),
                (field_names[2], "defines"),
            },
        )
        self.assertTrue(
            all(review.target_ids == ["qt-3"] for review in reconciled.reviews)
        )
        self.assertTrue(
            all(attribute.quantitative_target_ids == ["qt-3"] for attribute in projected)
        )

    def test_rejected_targets_remain_auditable_but_are_not_active_downstream(self) -> None:
        approved = QuantitativeTarget(
            id="qt-approved",
            expression=NumericExpression(
                kind="bound",
                unit="%",
                value=80,
                comparator=">=",
            ),
            role="threshold",
            quote="Target efficacy is at least 80%.",
            doc_block_ids=[BLOCK_ID],
            field_links=[
                QuantitativeFieldLink(
                    "vaccine.efficacy",
                    "defines",
                    "Direct efficacy requirement.",
                )
            ],
            semantic_profile={
                "measure": SemanticSlot(
                    state="specified",
                    value="protective efficacy",
                )
            },
            review_status="approved",
        )
        rejected = QuantitativeTarget(
            id="qt-rejected",
            expression=NumericExpression(
                kind="bound",
                unit="%",
                value=50,
                comparator=">=",
            ),
            role="threshold",
            quote="Background efficacy was at least 50%.",
            doc_block_ids=[BLOCK_ID],
            field_links=[
                QuantitativeFieldLink(
                    "vaccine.efficacy",
                    "context_for",
                    "Background context.",
                ),
                QuantitativeFieldLink(
                    "vaccine.product",
                    "constrains",
                    "Test fixture active link.",
                ),
            ],
            semantic_profile={
                "measure": SemanticSlot(
                    state="specified",
                    value="protective efficacy",
                )
            },
            review_status="rejected",
        )
        ledger = QuantitativeLedger(
            status="complete",
            reason="Reviewed targets.",
            block_ids=[BLOCK_ID],
            targets=[approved, rejected],
        )

        self.assertEqual(
            [target.id for target in _active_quantitative_targets(ledger)],
            [approved.id],
        )
        self.assertEqual(
            [target.id for target in ledger.targets],
            [approved.id, rejected.id],
        )

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

    def test_production_batches_interpret_each_shared_source_block_once(self) -> None:
        full_span = "Optimal: Dose volume <0.5 mL/dose; adult use only."
        first = Attribute(
            name="vaccine.dose_volume",
            description="Volume administered per dose",
            document_spans=[DocumentSpan(quote=full_span, block_ids=[BLOCK_ID])],
            target_resolved=True,
            target_resolution_reason="Resolved from an exact field span.",
        )
        second = Attribute(
            name="vaccine.programmatic_suitability",
            description="Programmatic requirements",
            document_spans=[DocumentSpan(quote=full_span, block_ids=[BLOCK_ID])],
            target_resolved=True,
            target_resolution_reason="Resolved from an exact field span.",
        )

        batches = prepare_quantitative_ledger_batches([_block()], [first, second])
        units = [unit for batch in batches for unit in batch.units]

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].quote, _block().content)
        self.assertEqual(
            units[0].candidate_attribute_refs,
            (first.name, second.name),
        )

    def test_shared_statement_is_one_claim_with_typed_field_links(self) -> None:
        block = ContentBlock(
            id="document/b-shared",
            doc_id="document",
            ordinal=3,
            block_type="table_row",
            content="Threshold: no more than two vials per administered dose.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        primary = Attribute(
            name="product.presentation",
            description="Container and presentation requirement",
            document_spans=[DocumentSpan(quote=block.content, block_ids=[block.id])],
            target_resolved=True,
        )
        related = Attribute(
            name="product.programmatic_suitability",
            description="Programmatic delivery requirement",
            document_spans=[DocumentSpan(quote=block.content, block_ids=[block.id])],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([block], [primary, related])[0]
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
            "value": "vials per administered dose",
            "other": "",
            "source_refs": ["statement"],
        }
        client = _LedgerClient([{
            "unit_id": unit.id,
            "classification": "target",
            "attribute_ref": primary.name,
            "reason": "The statement sets one presentation constraint.",
            "targets": [{
                "attribute_ref": primary.name,
                "related_attribute_refs": [related.name],
                "quote": block.content,
                "expression": {
                    "kind": "bound",
                    "unit": "vials/dose",
                    "value": 2,
                    "lower": None,
                    "upper": None,
                    "comparator": "<=",
                },
                "role": "threshold",
                "comparison_dimensions": ["measure"],
                "semantic_profile": profile,
                "ownership_reason": "Presentation directly owns vial count.",
            }],
        }])

        result = extract_quantitative_ledger_batch(
            batch,
            [primary, related],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )
        projected, ledger = assemble_quantitative_document_ledger(
            [primary, related], [batch], [result],
        )

        self.assertEqual(len(ledger.targets), 1)
        self.assertEqual(
            [(link.attribute_ref, link.relation) for link in ledger.targets[0].field_links],
            [(primary.name, "defines"), (related.name, "context_for")],
        )
        self.assertEqual(projected[0].quantitative_target_ids, [ledger.targets[0].id])
        self.assertEqual(projected[1].quantitative_target_ids, [])

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
        self.assertTrue(all(not attribute.quantitative_target_ids for attribute in finalized))

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
        self.assertEqual(attributes[0].quantitative_target_ids, [])
        self.assertEqual(len(attributes[1].quantitative_target_ids), 4)
        self.assertEqual(attributes[1].block_ids, [BLOCK_ID])
        self.assertIn("<0.5 mL/dose", attributes[1].document_target)
        self.assertEqual(
            attributes[1].document_spans,
            self.attributes[1].document_spans,
        )
        self.assertEqual(
            attributes[1].document_target,
            self.attributes[1].document_target,
        )
        self.assertEqual(
            {(target.role, target.semantic_profile["population"].value)
             for target in ledger.targets
             if target.id in attributes[1].quantitative_target_ids},
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

    def test_a_missing_statement_review_fails_after_one_targeted_retry(self) -> None:
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
        with self.assertRaisesRegex(
            ValueError,
            "incomplete schema-bound decisions for 1 statement",
        ):
            extract_quantitative_ledger_batch(
                self.batches[0],
                self.attributes,
                client,
                indication="malaria",
                intervention_class="vaccine",
            )
        self.assertEqual(client.calls, 2)

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
        self.assertEqual(
            client.schemas[1]["properties"]["reviews"]["minItems"],
            1,
        )

    def test_missing_response_retries_in_small_source_scoped_batches(self) -> None:
        blocks = [
            ContentBlock(
                id=f"document/b-{index:04d}",
                doc_id="document",
                ordinal=index,
                block_type="paragraph",
                content=f"Statement {index} contains context only.",
                heading_stack=[],
                structural_meta={},
                style_hint={},
            )
            for index in range(1, 7)
        ]
        batch = prepare_quantitative_ledger_batches(blocks)[0]
        client = _SequenceLedgerClient([[], [], []])

        with self.assertRaisesRegex(
            ValueError,
            "incomplete schema-bound decisions for 6 statement",
        ):
            extract_quantitative_ledger_batch(
                batch,
                [],
                client,
                indication="example condition",
                intervention_class="drug",
            )

        requested_ids = [
            schema["properties"]["reviews"]["items"]["properties"]
            ["unit_id"]["enum"]
            for schema in client.schemas
        ]
        self.assertEqual([len(ids) for ids in requested_ids], [6, 4, 2])
        self.assertEqual(
            requested_ids[1] + requested_ids[2],
            requested_ids[0],
        )

    def test_retry_preserves_valid_sibling_when_it_repairs_only_failed_target(self) -> None:
        source = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content="Pediatric dose <0.5 mL and adult dose <1.0 mL.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="vaccine.dose_volume",
            description="Volume administered per dose",
            document_spans=[DocumentSpan(quote=source.content, block_ids=[BLOCK_ID])],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([source])[0]
        unit = batch.units[0]
        valid = _target("Pediatric dose <0.5 mL", 0.5, "optimal", "pediatric")
        invalid = _target("adult dose under one mL", 1.0, "optimal", "adult")
        repaired = _target("adult dose <1.0 mL", 1.0, "optimal", "adult")
        client = _SequenceLedgerClient([
            [{
                "unit_id": unit.id,
                "classification": "target",
                "attribute_ref": attribute.name,
                "reason": "The statement defines pediatric and adult dose limits.",
                "targets": [valid, invalid],
            }],
            [{
                "unit_id": unit.id,
                "classification": "target",
                "attribute_ref": attribute.name,
                "reason": "The adult dose limit is stated directly.",
                "targets": [repaired],
            }],
        ])

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(result.reviews[0].classification, "target")
        self.assertEqual(result.reviews[0].review_status, "resolved")
        self.assertEqual(len(result.targets), 2)
        self.assertEqual(set(result.reviews[0].target_ids), {
            target.id for target in result.targets
        })

    def test_optional_unresolved_context_link_does_not_erase_valid_target(self) -> None:
        source = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content="Booster no more frequent than annually.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        resolved = Attribute(
            name="vaccine.dosing_schedule",
            description="Dosing schedule",
            document_spans=[DocumentSpan(quote=source.content, block_ids=[BLOCK_ID])],
            target_resolved=True,
        )
        unresolved = Attribute(
            name="vaccine.duration_of_protection",
            description="Duration of protection",
            target_resolved=False,
        )
        batch = prepare_quantitative_ledger_batches(
            [source], [resolved, unresolved]
        )[0]
        unit = batch.units[0]
        profile = _profile("general population")
        profile["measure"] = {
            "state": "specified",
            "value": "booster frequency",
            "other": "",
            "source_refs": ["statement"],
        }
        target = {
            **_target(source.content, 1, "threshold", "general population"),
            "expression": {
                "kind": "bound",
                "unit": "boosters/year",
                "value": 1,
                "lower": None,
                "upper": None,
                "comparator": "<=",
            },
            "semantic_profile": profile,
            "comparison_contract": _comparison_contract(profile, ("measure",)),
            "field_links": [
                {
                    "attribute_ref": resolved.name,
                    "relation": "defines",
                    "reason": "The statement defines booster frequency.",
                },
                {
                    "attribute_ref": unresolved.name,
                    "relation": "context_for",
                    "reason": "Optional related field view.",
                },
            ],
        }
        client = _SequenceLedgerClient([[
            {
                "unit_id": unit.id,
                "classification": "target",
                "attribute_refs": [resolved.name],
                "reason": "The statement sets a booster-frequency limit.",
                "targets": [target],
            }
        ]])

        result = extract_quantitative_ledger_batch(
            batch,
            [resolved, unresolved],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(len(result.targets), 1)
        self.assertEqual(
            [link.attribute_ref for link in result.targets[0].field_links],
            [resolved.name],
        )
        allowed_refs = (
            client.schemas[0]["properties"]["reviews"]["items"]["properties"]
            ["targets"]["items"]["properties"]["field_links"]["items"]
            ["properties"]["attribute_ref"]["enum"]
        )
        self.assertEqual(allowed_refs, [resolved.name])

    def test_retry_receives_precise_target_contract_failure(self) -> None:
        source = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content="Booster no more frequent than annually.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="vaccine.dosing_schedule",
            description="Dosing schedule",
            document_spans=[DocumentSpan(quote=source.content, block_ids=[BLOCK_ID])],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([source], [attribute])[0]
        unit = batch.units[0]
        profile = _profile("general population")
        profile["measure"] = {
            "state": "specified",
            "value": "booster frequency",
            "other": "",
            "source_refs": ["statement"],
        }
        valid_target = {
            **_target(source.content, 1, "threshold", "general population"),
            "expression": {
                "kind": "bound",
                "unit": "boosters/year",
                "value": 1,
                "lower": None,
                "upper": None,
                "comparator": "<=",
            },
            "semantic_profile": profile,
            "comparison_contract": _comparison_contract(profile, ("measure",)),
            "field_links": [{
                "attribute_ref": attribute.name,
                "relation": "defines",
                "reason": "The statement defines booster frequency.",
            }],
        }
        invalid_target = {
            **valid_target,
            "comparison_contract": {
                **valid_target["comparison_contract"],
                "measure": {
                    "mode": "compatible",
                    "scope": "booster frequency",
                    "reason": "Invalid fixture policy.",
                },
            },
        }
        review = {
            "unit_id": unit.id,
            "classification": "target",
            "attribute_refs": [attribute.name],
            "reason": "The statement sets a booster-frequency limit.",
        }
        client = _SequenceLedgerClient([
            [{**review, "targets": [invalid_target]}],
            [{**review, "targets": [valid_target]}],
        ])

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(len(result.targets), 1)
        self.assertIn(
            "incomplete direct-comparator policy",
            client.user_messages[1],
        )

    def test_retry_retains_valid_sibling_when_other_target_stays_unresolved(self) -> None:
        source = ContentBlock(
            id=BLOCK_ID,
            doc_id="document",
            ordinal=1,
            block_type="paragraph",
            content="Pediatric dose <0.5 mL and adult dose <1.0 mL.",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        attribute = Attribute(
            name="vaccine.dose_volume",
            description="Volume administered per dose",
            document_spans=[DocumentSpan(quote=source.content, block_ids=[BLOCK_ID])],
            target_resolved=True,
        )
        batch = prepare_quantitative_ledger_batches([source])[0]
        unit = batch.units[0]
        valid = _target("Pediatric dose <0.5 mL", 0.5, "optimal", "pediatric")
        invalid = _target("adult dose under one mL", 1.0, "optimal", "adult")
        response = [{
            "unit_id": unit.id,
            "classification": "target",
            "attribute_ref": attribute.name,
            "reason": "The statement defines pediatric and adult dose limits.",
            "targets": [valid, invalid],
        }]

        result = extract_quantitative_ledger_batch(
            batch,
            [attribute],
            _SequenceLedgerClient([response, response]),
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(result.reviews[0].classification, "partial_target")
        self.assertEqual(result.reviews[0].review_status, "needs_review")
        self.assertEqual(len(result.targets), 1)
        self.assertEqual(result.reviews[0].target_ids, [result.targets[0].id])
        self.assertIn("Source-verifiable targets were retained", result.reviews[0].reason)

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

    def test_cross_block_context_projects_only_when_ai_links_the_field(self) -> None:
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

        self.assertEqual(ledger.reviews[0].attribute_refs, [attribute.name])
        self.assertEqual(
            [item.disposition for item in attributes[0].quantitative_statement_dispositions],
            ["non_scalar"],
        )
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
