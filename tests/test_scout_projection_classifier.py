from __future__ import annotations

import copy
import threading
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


class _PerRequestClient:
    """Answer each contained request from its own schema, like a real endpoint.

    Contained requests are dispatched concurrently, so a stub that popped a
    shared response queue would pair answers with requests by arrival order.
    """

    def __init__(self, decisions: dict[str, tuple[str, str]]) -> None:
        self.decisions = decisions
        self._lock = threading.Lock()
        self.requested_ids: list[list[str]] = []

    def call_structured(self, *_args, **kwargs):
        requested = list(
            kwargs["schema"]["properties"]["relationships"]["items"]
            ["properties"]["projection_id"]["enum"]
        )
        with self._lock:
            self.requested_ids.append(requested)
        return {"relationships": [
            {
                "projection_id": projection_id,
                "target_relationship": self.decisions[projection_id][0],
                "reason": self.decisions[projection_id][1],
            }
            for projection_id in requested
            if projection_id in self.decisions
        ]}


class _MalformedClient:
    """Return one invalid payload for every request, whatever was asked."""

    def __init__(self, relationships: list[dict]) -> None:
        self.relationships = relationships

    def call_structured(self, *_args, **_kwargs):
        return {"relationships": self.relationships}


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
        client = _PerRequestClient({
            "dp-a": ("direct", "Same product candidate."),
            "dp-b": ("analogous", "Different candidate in the same product class."),
            "so-c": ("adjacent", "Relevant safety context for another product class."),
        })

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

    def test_each_projection_is_classified_in_its_own_request(self) -> None:
        """A per-item relationship must not be judged alongside unrelated items."""
        programs = [
            DevelopmentProgram(name="A", projection_id="dp-a"),
            DevelopmentProgram(name="B", projection_id="dp-b"),
        ]
        client = _PerRequestClient({
            "dp-a": ("direct", "Same product candidate."),
            "dp-b": ("adjacent", "Relevant context for another product class."),
        })

        classified, _ = classify_projection_relationships(
            [_attribute()],
            programs,
            [],
            client,
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(sorted(client.requested_ids), [["dp-a"], ["dp-b"]])
        self.assertEqual(
            [item.target_relationship for item in classified],
            ["direct", "adjacent"],
        )

    def test_omitted_invalid_duplicate_and_unknown_ids_degrade_to_unknown(self) -> None:
        programs = [
            DevelopmentProgram(name="A", projection_id="dp-a"),
            DevelopmentProgram(name="B", projection_id="dp-b"),
            DevelopmentProgram(name="C", projection_id="dp-c"),
        ]
        client = _MalformedClient([
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
        ])

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
