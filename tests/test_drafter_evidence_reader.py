"""Reading one source for one variable: what it says, in its own words."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.drafter.stages.evidence_reader import (
    FINDINGS_PER_REQUEST,
    MAX_FINDINGS_PER_VARIABLE,
    eligible_findings,
    read_finding,
)
from services.searcher import Finding
from shared.vocabulary import AttributeDefinition
from tests.drafter_support import ScriptedClient

EFFICACY = AttributeDefinition("vaccine.efficacy", "Protective efficacy.", "clinical")
EXCERPT = "In children aged 5-17 months, RTS,S efficacy against clinical malaria was 56% (95% CI 51-60) over 12 months."


def finding(lane: str = "pubmed", excerpt: str | None = EXCERPT, role: str = "evidence", url: str = "https://pubmed.org/1") -> Finding:
    return Finding(url=url, title="RTS,S phase 3", query="q", retrieved_at=datetime.now(timezone.utc),
                   excerpt=excerpt, source=lane, source_lanes=[lane], excerpt_source_lane=lane, evidence_role=role,
                   source_labels={lane: lane.title()})


def item(quote: str, basis: str = "comparable_product", value: float | None = 56.0, unit: str = "%") -> dict:
    return {"basis": basis, "product": "RTS,S/AS01", "measure": "efficacy against clinical malaria",
            "quote": quote, "value": value, "lower": None, "upper": None, "unit": unit}


class EligibilityTests(unittest.TestCase):
    def test_only_evidence_with_an_excerpt_is_read_and_the_count_is_bounded(self):
        findings = [finding(url=f"https://pubmed.org/{n}") for n in range(MAX_FINDINGS_PER_VARIABLE + 3)]
        findings += [finding(excerpt=None, url="https://x.org/none"), finding(role="reference", url="https://x.org/ref")]
        chosen = eligible_findings(findings)
        self.assertEqual(len(chosen), MAX_FINDINGS_PER_VARIABLE)
        self.assertTrue(all(found.excerpt for found in chosen))
        self.assertEqual(FINDINGS_PER_REQUEST, 1)


class ReadingBudgetTests(unittest.TestCase):
    def test_the_reading_budget_is_shared_across_sources_not_spent_on_the_first(self):
        # A general web lane listed first returns many results; the literature behind it
        # must still be read, or no figure could ever be computed.
        findings = [finding(lane="tavily", url=f"https://web.org/{n}") for n in range(12)]
        findings += [finding(lane="pubmed", url=f"https://pubmed.org/{n}") for n in range(3)]
        findings += [finding(lane="who_guidelines", url="https://who.int/g")]
        chosen = eligible_findings(findings)
        lanes = [found.excerpt_source_lane for found in chosen]
        self.assertEqual(len(chosen), MAX_FINDINGS_PER_VARIABLE)
        self.assertEqual(lanes.count("pubmed"), 3)
        self.assertEqual(lanes.count("who_guidelines"), 1)
        self.assertEqual(lanes[:3], ["tavily", "pubmed", "who_guidelines"])


class ReadFindingTests(unittest.TestCase):
    def read(self, source: Finding, *replies):
        client = ScriptedClient({"vaccine.efficacy": list(replies)})
        return read_finding(EFFICACY, source, client, indication="malaria", intervention_term="vaccine"), client

    def test_a_quoted_value_from_literature_may_enter_statistics(self):
        found, _ = self.read(finding(), {"observations": [item("RTS,S efficacy against clinical malaria was 56%")]})
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].numeric_eligible)
        self.assertEqual(found[0].value.unit, "%")
        self.assertEqual(found[0].source_label, "Pubmed")

    def test_a_quote_the_excerpt_does_not_contain_is_dropped(self):
        found, _ = self.read(finding(), {"observations": [item("efficacy was 90%")]})
        self.assertEqual(found, [])

    def test_quotes_match_across_whitespace_and_typographic_quotes(self):
        source = finding(excerpt="The vaccine’s efficacy\nwas 56% overall.")
        found, _ = self.read(source, {"observations": [item("The vaccine's efficacy was 56% overall.")]})
        self.assertEqual(len(found), 1)

    def test_a_web_search_snippet_never_supplies_a_number(self):
        found, _ = self.read(finding(lane="tavily"), {"observations": [item("RTS,S efficacy against clinical malaria was 56%")]})
        self.assertFalse(found[0].numeric_eligible)

    def test_a_guidance_target_is_kept_but_never_enters_statistics(self):
        source = finding(lane="who_guidelines", excerpt="A malaria vaccine should have efficacy of at least 75% against clinical malaria.")
        found, _ = self.read(source, {"observations": [item("efficacy of at least 75% against clinical malaria", basis="published_guidance", value=75.0)]})
        self.assertEqual(found[0].basis, "published_guidance")
        self.assertFalse(found[0].numeric_eligible)

    def test_an_unusable_reply_is_retried_once_then_the_source_is_skipped(self):
        found, client = self.read(finding(), None, None)
        self.assertIsNone(found)
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
