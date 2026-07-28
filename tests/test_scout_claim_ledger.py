from __future__ import annotations

import unittest

from services.scout.models import Attribute
from services.scout.context import (
    render_line_addressable_context,
    rendered_block_texts,
    selected_source_lines,
)
from services.scout.stages.target_resolver import resolve_document_targets


class _Client:
    def __init__(self, bindings: list[dict]):
        self.bindings = bindings
        self.calls = 0

    def call_structured(self, *_args, schema, **_kwargs) -> dict:
        self.calls += 1
        return {next(iter(schema["properties"])): self.bindings}


class _SequenceClient:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.calls = 0

    def call_structured(self, *_args, schema, **_kwargs) -> dict:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return {next(iter(schema["properties"])): response}


class _StructuredSequenceClient:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.calls = 0
        self.schemas: list[dict] = []

    def call_structured(self, *_args, schema, **_kwargs):
        self.schemas.append(schema)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return {"bindings": response}


def _binding(attribute_ref: str, quote: str, block_id: str) -> dict:
    return {
        "attribute_ref": attribute_ref,
        "status": "present",
        "reason": "The cited statement directly defines this field.",
        "spans": [{"block_id": block_id, "start_line": 1, "end_line": 1}],
        "entities": [],
    }


class DocumentClaimLedgerTests(unittest.TestCase):
    def test_line_selection_copies_exact_multiline_source_text(self) -> None:
        context = (
            "[block:DRAFT AIV iTPP/b-0089]\n"
            "Variable: Dosing Schedule\n"
            "Two doses (prime-boost configuration).\n"
            "No booster."
        )

        self.assertIn(
            "[line:2] Two doses (prime-boost configuration).",
            render_line_addressable_context(context),
        )
        self.assertEqual(
            selected_source_lines(
                {
                    "block_id": "DRAFT AIV iTPP/b-0089",
                    "start_line": 2,
                    "end_line": 3,
                },
                rendered_block_texts(context),
            ),
            (
                "Two doses (prime-boost configuration).\nNo booster.",
                "DRAFT AIV iTPP/b-0089",
            ),
        )

    def test_large_catalog_is_batched_without_losing_full_coverage(self) -> None:
        attributes = [
            Attribute(name=f"drug.field_{index}", description=f"Field {index}")
            for index in range(13)
        ]
        bindings = [
            {
                "attribute_ref": attribute.name,
                "status": "absent",
                "reason": "The field is not stated in this document.",
                "spans": [],
                "entities": [],
            }
            for attribute in attributes
        ]
        client = _Client(bindings)

        resolved = resolve_document_targets(
            attributes,
            "[block:document/b-0001]\nDocument overview.",
            client,
        )

        self.assertEqual(client.calls, 3)
        self.assertTrue(all(attribute.target_resolved for attribute in resolved))
        self.assertTrue(all(not attribute.document_target for attribute in resolved))

    def test_missing_decision_is_retried_once_without_rerunning_valid_fields(self) -> None:
        dose = Attribute(name="drug.dose", description="Dose")
        timeline = Attribute(name="drug.timeline", description="Timeline")
        dose_binding = _binding(
            dose.name,
            "Dose is 50 mg.",
            "document/b-0001",
        )
        timeline_binding = _binding(
            timeline.name,
            "Approval is targeted for 2028.",
            "document/b-0002",
        )
        client = _StructuredSequenceClient([
            [dose_binding],
            [timeline_binding],
        ])

        resolved = resolve_document_targets(
            [dose, timeline],
            "[block:document/b-0001]\nDose is 50 mg.\n\n"
            "[block:document/b-0002]\nApproval is targeted for 2028.",
            client,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(
            [attribute.document_target for attribute in resolved],
            ["Dose is 50 mg.", "Approval is targeted for 2028."],
        )
        first_refs = (
            client.schemas[0]["properties"]["bindings"]["items"]["properties"]
            ["attribute_ref"]["enum"]
        )
        retry_refs = (
            client.schemas[1]["properties"]["bindings"]["items"]["properties"]
            ["attribute_ref"]["enum"]
        )
        self.assertEqual(first_refs, [dose.name, timeline.name])
        self.assertEqual(retry_refs, [timeline.name])

    def test_one_generic_contract_binds_cross_domain_claim_shapes(self) -> None:
        cases = [
            ("vaccine.efficacy", "Protective efficacy must exceed 80% at 12 months."),
            ("drug.dose", "The daily oral dose is 50 mg."),
            ("diagnostic.lod", "Limit of detection must be below 10 copies/mL."),
            ("device.storage", "The device must tolerate storage at 45 C."),
        ]
        attributes = [
            Attribute(name=name, description=f"Definition for {name}")
            for name, _ in cases
        ]
        blocks = [
            f"[block:document/b-{index:04d}]\n{quote}"
            for index, (_, quote) in enumerate(cases, start=1)
        ]
        client = _Client(
            [
                _binding(name, quote, f"document/b-{index:04d}")
                for index, (name, quote) in enumerate(cases, start=1)
            ]
        )

        resolved = resolve_document_targets(
            attributes,
            "\n\n".join(blocks),
            client,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(
            [(item.name, item.document_target) for item in resolved],
            cases,
        )
        self.assertTrue(all(item.target_resolved for item in resolved))

    def test_invalid_or_missing_field_fails_closed_without_erasing_valid_fields(self) -> None:
        attributes = [
            Attribute(name="drug.dose", description="Dose"),
            Attribute(name="drug.timeline", description="Development timeline"),
        ]
        client = _Client(
            [
                _binding("drug.dose", "Dose is 50 mg.", "document/b-0001"),
                {
                    "attribute_ref": "drug.timeline",
                    "status": "present",
                    "reason": "Timeline",
                    "spans": [
                        {
                            "block_id": "document/b-0002",
                            "start_line": 2,
                            "end_line": 2,
                        }
                    ],
                    "entities": [],
                },
            ]
        )

        resolved = resolve_document_targets(
            attributes,
            "[block:document/b-0001]\nDose is 50 mg.\n\n"
            "[block:document/b-0002]\nNo approval date is stated.",
            client,
        )

        self.assertEqual(resolved[0].document_target, "Dose is 50 mg.")
        self.assertTrue(resolved[0].target_resolved)
        self.assertEqual(resolved[1].document_target, "")
        self.assertFalse(resolved[1].target_resolved)
        self.assertIn(
            "invalid or empty source line range in document/b-0002",
            resolved[1].target_resolution_reason,
        )

    def test_unknown_block_is_reported_without_silently_dropping_it(self) -> None:
        attribute = Attribute(name="drug.dose", description="Dose")
        client = _Client(
            [
                {
                    "attribute_ref": attribute.name,
                    "status": "present",
                    "reason": "Dose",
                    "spans": [
                        {
                            "block_id": "document/b-9999",
                            "start_line": 1,
                            "end_line": 1,
                        }
                    ],
                    "entities": [],
                }
            ]
        )

        resolved = resolve_document_targets(
            [attribute],
            "[block:document/b-0001]\nDose is 50 mg.",
            client,
        )[0]

        self.assertFalse(resolved.target_resolved)
        self.assertEqual(
            resolved.target_resolution_reason,
            "A supporting span cited an unknown document block ID: document/b-9999.",
        )

    def test_missing_present_spans_has_a_distinct_diagnostic(self) -> None:
        attribute = Attribute(name="drug.dose", description="Dose")
        client = _Client(
            [
                {
                    "attribute_ref": attribute.name,
                    "status": "present",
                    "reason": "Dose",
                    "spans": [],
                    "entities": [],
                }
            ]
        )

        resolved = resolve_document_targets(
            [attribute],
            "[block:document/b-0001]\nDose is 50 mg.",
            client,
        )[0]

        self.assertFalse(resolved.target_resolved)
        self.assertEqual(
            resolved.target_resolution_reason,
            "The present decision returned no supporting document spans.",
        )

    def test_dynamic_claims_pass_through_without_another_model_interpretation(self) -> None:
        dynamic = Attribute(
            name="phase_2_timeline",
            description="Timing of the Phase 2 milestone.",
            document_target="Complete Phase 2 by 2028.",
            block_ids=["document/b-0001"],
            definition_mode="dynamic",
            target_resolved=True,
        )
        client = _Client([])

        self.assertEqual(
            resolve_document_targets([dynamic], "", client),
            [dynamic],
        )
        self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
