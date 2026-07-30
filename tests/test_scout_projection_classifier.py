from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from services.scout.models import Attribute, DevelopmentProgram, SafetyObservation
from services.scout.stages.projection_classifier import (
    classify_projection_relationships,
)
from services.searcher import Finding


class StructuredClient:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def call_structured(self, *_args, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _finding(url: str, title: str) -> Finding:
    return Finding(
        url=url,
        title=title,
        query="malaria candidate",
        retrieved_at=datetime.now(timezone.utc),
        excerpt="A structured source record describes this candidate.",
        source="clinicaltrials",
    )


def _attribute() -> Attribute:
    attribute = Attribute(
        name="Clinical Efficacy",
        description="Protective efficacy required by the product profile.",
    )
    attribute.document_target = "Target efficacy greater than 80%."
    attribute.target_resolved = True
    return attribute


class ProjectionClassifierTests(unittest.TestCase):
    def test_applies_only_valid_id_bound_relationship_decisions(self) -> None:
        attributes = [_attribute()]
        findings = [_finding("https://example.test/a", "Candidate A trial")]
        programs = [
            DevelopmentProgram(
                name="Candidate A",
                projection_id="dp-a",
                source_role="experimental",
                supporting_findings=findings,
            ),
            DevelopmentProgram(
                name="Candidate B",
                projection_id="dp-b",
                supporting_findings=[
                    _finding("https://example.test/b", "Candidate B trial")
                ],
            ),
        ]
        observations = [
            SafetyObservation(
                product_name="Candidate C",
                record_type="reported_event",
                source_system="faers",
                label="Headache",
                report_count=12,
                projection_id="so-c",
                supporting_findings=[
                    _finding("https://example.test/c", "Candidate C safety")
                ],
            )
        ]
        attributes_before = copy.deepcopy(attributes)
        findings_before = copy.deepcopy(findings)
        client = StructuredClient(
            [
                {
                    "relationships": [
                        {
                            "projection_id": "dp-a",
                            "target_relationship": "direct",
                            "reason": "Same product candidate.",
                        },
                        {
                            "projection_id": "dp-b",
                            "target_relationship": "analogous",
                            "reason": "Different candidate in the same product class.",
                        },
                        {
                            "projection_id": "so-c",
                            "target_relationship": "adjacent",
                            "reason": "Relevant safety context for another product class.",
                        },
                    ]
                }
            ]
        )

        classified_programs, classified_observations = classify_projection_relationships(
            attributes,
            programs,
            observations,
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(
            [item.target_relationship for item in classified_programs],
            ["direct", "analogous"],
        )
        self.assertEqual(
            classified_observations[0].target_relationship,
            "adjacent",
        )
        self.assertEqual(
            classified_programs[0].target_relationship_reason,
            "Same product candidate.",
        )
        self.assertEqual(attributes, attributes_before)
        self.assertEqual(findings, findings_before)
        self.assertEqual(programs[0].target_relationship, "unknown")

    def test_omitted_invalid_duplicate_and_unknown_ids_degrade_to_unknown(self) -> None:
        programs = [
            DevelopmentProgram(name="A", projection_id="dp-a"),
            DevelopmentProgram(name="B", projection_id="dp-b"),
            DevelopmentProgram(name="C", projection_id="dp-c"),
        ]
        client = StructuredClient(
            [
                {
                    "relationships": [
                        {
                            "projection_id": "dp-a",
                            "target_relationship": "direct",
                            "reason": "First decision.",
                        },
                        {
                            "projection_id": "dp-a",
                            "target_relationship": "analogous",
                            "reason": "Conflicting duplicate.",
                        },
                        {
                            "projection_id": "dp-b",
                            "target_relationship": "invented",
                            "reason": "Invalid enum.",
                        },
                        {
                            "projection_id": "dp-unknown",
                            "target_relationship": "direct",
                            "reason": "Unknown ID.",
                        },
                    ]
                }
            ]
        )

        classified, _ = classify_projection_relationships(
            [_attribute()],
            programs,
            [],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(
            [item.target_relationship for item in classified],
            ["unknown", "unknown", "unknown"],
        )

    def test_provider_failure_is_confined_to_projection_relationships(self) -> None:
        program = DevelopmentProgram(name="A", projection_id="dp-a")
        client = StructuredClient([RuntimeError("provider unavailable")])

        classified, signals = classify_projection_relationships(
            [_attribute()],
            [program],
            [],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(classified[0].target_relationship, "unknown")
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
