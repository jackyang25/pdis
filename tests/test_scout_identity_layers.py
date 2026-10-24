"""Scout's identity layers decide sameness one way, and fail one way.

Program and product names, a field's insights, numeric targets and extracted claims are
each partitioned by one model call over their set. No layer folds strings to decide two
items are one, and every layer that cannot obtain a partition keeps its items apart and
records why, with a code.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import httpx
import openai

from services.scout.lineage import RetrievalLineage
from services.scout.projections import build_development_landscape, build_safety_observations
from services.scout.stages.projection_reconciler import reconcile_projection_names
from services.searcher import (
    DevelopmentRecord,
    Finding,
    RetrievalPath,
    SafetyObservationRecord,
    SearchRequest,
)


def _finding(url: str, *, programs=(), products=(), record_key: str = "") -> Finding:
    return Finding(
        url=url,
        title=url,
        query="rsv vaccine",
        retrieved_at=datetime.now(timezone.utc),
        source="clinicaltrials",
        record_key=record_key,
        development_records=[
            DevelopmentRecord(program_name=name, record_type="clinical_trial", phase="Phase 3")
            for name in programs
        ],
        safety_observations=[
            SafetyObservationRecord(
                product_name=name, record_type="label_warning", source_system="fda_label",
                label="Preterm birth",
            )
            for name in products
        ],
    )


class _Partitions:
    def __init__(self, groups: list[list[str]]) -> None:
        self.groups = groups
        self.payloads: list[str] = []

    def call_structured(self, _system, message, *_args, **kwargs):
        self.payloads.append(message)
        import json

        names = {item["name"]: item["name_id"] for item in json.loads(message)}
        return {"groups": [
            {"representative_name_id": names[group[0]],
             "member_name_ids": [names[name] for name in group]}
            for group in self.groups
        ]}


class _Down:
    def call_structured(self, *_args, **_kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://provider.test"))


class ProjectionIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.findings = {
            "vaccine.efficacy": [
                _finding("https://a.test", programs=["RSVpreF"], record_key="clinicaltrials:NCT1"),
                _finding("https://b.test", programs=["Abrysvo"], record_key="clinicaltrials:NCT2"),
            ],
            "vaccine.safety": [
                _finding("https://c.test", products=["ABRYSVO"], record_key="fda:label:x"),
            ],
        }

    def test_names_the_model_groups_become_one_program_and_one_product(self) -> None:
        names, record = reconcile_projection_names(
            self.findings, _Partitions([["Abrysvo", "RSVpreF", "ABRYSVO"]]),
        )
        landscape = build_development_landscape(self.findings, names)
        safety = build_safety_observations(self.findings, names)

        self.assertEqual([program.name for program in landscape], ["Abrysvo"])
        self.assertEqual(len(landscape[0].supporting_findings), 2)
        self.assertEqual([observation.product_name for observation in safety], ["Abrysvo"])
        self.assertEqual((record.layer, record.status, record.merged), ("projections", "reconciled", 2))

    def test_names_differing_only_in_case_are_not_merged_by_code(self) -> None:
        """Without the identity layer's answer, "ABRYSVO" and "Abrysvo" stay apart."""
        findings = {
            "vaccine.efficacy": [
                _finding("https://a.test", programs=["Abrysvo"], record_key="clinicaltrials:NCT1"),
                _finding("https://b.test", programs=["ABRYSVO"], record_key="clinicaltrials:NCT2"),
            ],
        }
        self.assertEqual(len(build_development_landscape(findings)), 2)

    def test_a_failed_partition_keeps_every_name_and_records_its_code(self) -> None:
        names, record = reconcile_projection_names(self.findings, _Down())

        self.assertEqual(names, {name: name for name in ("RSVpreF", "Abrysvo", "ABRYSVO")})
        self.assertEqual((record.status, record.failure_code), ("not_reconciled", "provider_error"))
        self.assertEqual(len(build_development_landscape(self.findings, names)), 2)

    def test_one_name_needs_no_call(self) -> None:
        names, record = reconcile_projection_names(
            {"vaccine.efficacy": [_finding("https://a.test", programs=["RSVpreF"])]}, _Down(),
        )
        self.assertEqual((names, record), ({"RSVpreF": "RSVpreF"}, None))

    def test_one_record_reached_twice_is_listed_once(self) -> None:
        findings = {
            "vaccine.efficacy": [_finding("https://a.test", programs=["RSVpreF"], record_key="clinicaltrials:NCT1")],
            "vaccine.safety": [_finding("https://a.test", programs=["RSVpreF"], record_key="clinicaltrials:NCT1")],
        }
        [program] = build_development_landscape(findings)
        self.assertEqual(len(program.supporting_findings), 1)
        self.assertEqual(program.attribute_refs, ["vaccine.efficacy", "vaccine.safety"])


class RetrievalLineageTests(unittest.TestCase):
    """An insight's tracks come from the requests that found its records."""

    def test_lineage_is_read_from_the_finding_path_not_from_query_text(self) -> None:
        general = SearchRequest(scope_ref="efficacy", source="pubmed", query="rsv efficacy",
                                tracks=("general",), target_refs=("qt-1",))
        precedent = SearchRequest(scope_ref="efficacy", source="europepmc", query="rsv efficacy",
                                  tracks=("precedent",))
        lineage = RetrievalLineage([general, precedent])
        finding = Finding(
            url="https://pubmed.test/1", title="t", query="rsv efficacy",
            retrieved_at=datetime.now(timezone.utc), source="pubmed",
            retrieval_paths=[RetrievalPath(query="rsv efficacy", lane="pubmed")],
        )

        # The same query text went to two lanes; only the lane that returned it counts.
        self.assertEqual(lineage.tracks("efficacy", [finding]), ["general"])
        self.assertEqual(lineage.target_ids("efficacy", [finding]), ["qt-1"])
        self.assertEqual(lineage.tracks("safety", [finding]), [])


if __name__ == "__main__":
    unittest.main()
