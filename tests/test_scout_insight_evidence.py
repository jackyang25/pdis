"""The judging stages see the records an insight rests on, and all three see the same.

Drift, grounding and precedent weigh recency, study design and regulatory relevance,
and were shown only the insight's paraphrase and its URLs. Each now sees every
supporting record's title, lane and evidence class, publication date at its stated
precision, excerpt kind and opening - rendered once, for all three.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.insight_evidence import (
    VERDICT_EXCERPT_CHARS,
    render_insight_evidence,
)
from services.scout.models import Attribute, DocumentSpan, Insight
from services.scout.stages.drift_classifier import classify_drift
from services.scout.stages.evidence_assessor import assess_evidence
from services.scout.stages.precedent_classifier import classify_precedent
from services.searcher import Finding

BINDING = "[block:doc/b-1]\nEfficacy of at least 60% against MA-LRTI."


def _finding(**overrides) -> Finding:
    values = dict(
        url="https://pubmed.ncbi.nlm.nih.gov/1/",
        title="Bivalent prefusion F vaccine in pregnancy",
        query="rsv maternal vaccine efficacy",
        retrieved_at=datetime.now(timezone.utc),
        source="pubmed",
        excerpt="Randomised placebo-controlled phase 3 trial. " + "word " * 400,
        published_at=datetime(2023, 4, 1, tzinfo=timezone.utc),
        published_precision="month",
    )
    values.update(overrides)
    return Finding(**values)


def _insight() -> Insight:
    return Insight(
        statement="Vaccine efficacy against MA-LRTI was 57% through 180 days.",
        supporting_findings=[_finding()],
        attribute_ref="vaccine.efficacy",
    )


class RenderingTests(unittest.TestCase):
    def test_a_record_shows_its_source_class_date_and_excerpt_opening(self) -> None:
        text = render_insight_evidence(_insight(), label="[0]")

        self.assertIn("Bivalent prefusion F vaccine in pregnancy", text)
        self.assertIn("(literature evidence)", text)
        self.assertIn("2023-04 (month only)", text)
        self.assertIn("the source's own text", text)
        self.assertIn("Randomised placebo-controlled phase 3 trial.", text)
        excerpt_line = next(line for line in text.splitlines() if "excerpt (" in line)
        self.assertLess(len(excerpt_line), VERDICT_EXCERPT_CHARS + 120)

    def test_a_generated_excerpt_says_it_is_not_the_source(self) -> None:
        insight = _insight()
        insight.supporting_findings = [_finding(source="web", excerpt_kind="generated")]
        self.assertIn("not the source's own words", render_insight_evidence(insight, label="[0]"))

    def test_a_record_is_dated_at_its_stated_precision_or_says_it_is_undated(self) -> None:
        insight = _insight()
        insight.supporting_findings = [_finding(published_at=None)]
        self.assertIn("published: not stated by the source", render_insight_evidence(insight, label="[0]"))
        insight.supporting_findings = [_finding(published_precision="year")]
        self.assertIn("published: 2023 (year only)", render_insight_evidence(insight, label="[0]"))


class _Recorder:
    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.trailing: list[str] = []

    def call_structured(self, _system, _message, _max_tokens, **kwargs):
        self.trailing.append(kwargs["trailing_text"])
        return self.reply


class SharedEvidenceTests(unittest.TestCase):
    def test_all_three_verdict_stages_see_the_same_record_details(self) -> None:
        attribute = Attribute(
            "vaccine.efficacy", "Efficacy.",
            document_spans=[DocumentSpan(quote="Efficacy of at least 60% against MA-LRTI.",
                                         block_ids=["doc/b-1"])],
            target_resolved=True,
        )
        drift = _Recorder({"match": {"relation": "unrelated", "reason": "x", "doc_block_ids": []}})
        evidence = _Recorder({"assessment": {"strength": "unknown", "reason": "x",
                                             "supporting_insight_indices": []}})
        precedent = _Recorder({"assessment": {
            "precedent": "unknown", "outcome": "unknown", "reason": "x",
            "coverage_insight_indices": [], "outcome_insight_indices": [],
        }})
        options = dict(indication="rsv", intervention_class="vaccine")
        classify_drift(BINDING, _insight(), drift, **options)
        assess_evidence(attribute, BINDING, [_insight()], evidence, **options)
        classify_precedent(attribute, BINDING, [_insight()], precedent, **options)

        rendered = render_insight_evidence(_insight(), label="")
        record_lines = [line for line in rendered.splitlines() if line.startswith("      ")]
        for recorder in (drift, evidence, precedent):
            for line in record_lines:
                self.assertIn(line, recorder.trailing[0])


if __name__ == "__main__":
    unittest.main()
