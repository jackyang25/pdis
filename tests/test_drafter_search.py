"""Planning each variable's searches, and gathering what the sources returned."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from services.drafter import find_config
from services.drafter.retrieval import retrieve
from services.drafter.stages.search_planner import QUERIES_PER_VARIABLE, plan_searches
from services.searcher import Finding
from shared.errors import ModelResponseError
from shared.vocabulary import AttributeDefinition
from tests.drafter_support import ScriptedClient

EFFICACY = AttributeDefinition("vaccine.efficacy", "Protective efficacy against the primary endpoint.", "clinical")
CONFIG = find_config("bmgf", "itpp", "vaccine")


def query(text: str, purpose: str = "comparable") -> dict:
    return {"query": text, "purpose": purpose,
            "facets": {"condition": "malaria", "intervention": "vaccine", "population": "children", "outcome": "clinical malaria"}}


class SearchPlannerTests(unittest.TestCase):
    def plan(self, *replies):
        client = ScriptedClient({"Variable: vaccine.efficacy": list(replies)})
        return plan_searches(EFFICACY, CONFIG, client, indication="malaria", intervention_term="vaccine"), client

    def test_one_intent_per_variable_carries_both_purposes(self):
        intent, client = self.plan({"queries": [query("RTS,S efficacy children"), query("WHO malaria vaccine PPC efficacy", "guidance")]})
        self.assertEqual(intent.scope_ref, "vaccine.efficacy")
        self.assertEqual(intent.indication, "malaria")
        self.assertEqual([q.tracks for q in intent.queries], [("comparable",), ("guidance",)])
        self.assertEqual(intent.queries[0].facets.population, "children")
        self.assertIn(CONFIG.query_guidance.strip()[:40], client.calls[0][0])

    def test_every_query_the_plan_wrote_is_kept_in_its_order(self):
        """Not deduplicated by text: Searcher collapses identical native requests and keeps
        both queries' lineage, which comparing strings here would lose."""
        intent, _ = self.plan({"queries": [query("RTS,S efficacy"), query("rts,s  efficacy")]})
        self.assertEqual([q.text for q in intent.queries], ["RTS,S efficacy", "rts,s efficacy"])

    def test_the_policy_is_the_stage_s_own(self):
        _, client = self.plan({"queries": [query("RTS,S efficacy")]})
        call = client.calls[0][2]
        self.assertEqual((call["task"], call["effort"]), ("fast", "low"))

    def test_the_schema_states_the_bounds_the_code_enforces(self):
        # A validator refusing what its own schema permits makes answers the model cannot get right.
        from services.drafter.stages.search_planner import SCHEMA
        queries = SCHEMA["properties"]["queries"]
        self.assertEqual((queries["minItems"], queries["maxItems"]), (1, QUERIES_PER_VARIABLE))
        self.assertEqual(queries["items"]["properties"]["query"]["pattern"], "\\S")

    def test_no_usable_query_is_retried_once_then_fails(self):
        intent, client = self.plan({"queries": []}, {"queries": [query("RTS,S efficacy")]})
        self.assertEqual(len(intent.queries), 1)
        self.assertEqual(len(client.calls), 2)
        with self.assertRaises(ModelResponseError):
            self.plan({"queries": []}, {"queries": [query(" ")]})

    def test_a_repair_note_names_what_was_wrong(self):
        _, client = self.plan({"queries": [query(" ")]}, {"queries": [query("RTS,S efficacy")]})
        self.assertIn("blank", client.calls[1][1])


def finding(url: str, source: str) -> Finding:
    return Finding(url=url, title=url, query="q", retrieved_at=datetime.now(timezone.utc),
                   excerpt="text", source=source, source_lanes=[source], excerpt_source_lane=source)


def outcome(scope: str, source: str, status: str, *findings: Finding, error: str = ""):
    return SimpleNamespace(request=SimpleNamespace(scope_ref=scope, source=source), status=status, findings=list(findings), error=error)


class RetrievalTests(unittest.TestCase):
    def test_findings_are_grouped_by_variable_and_failed_sources_reported(self):
        outcomes = [
            outcome("vaccine.efficacy", "pubmed", "complete", finding("https://a.org/1", "pubmed")),
            outcome("vaccine.efficacy", "europepmc", "complete", finding("https://a.org/1", "europepmc")),
            outcome("vaccine.safety", "pubmed", "complete", finding("https://a.org/2", "pubmed")),
            outcome("vaccine.safety", "fda", "failed", error="openFDA returned HTTP 503"),
        ]
        outcomes.append(outcome("vaccine.efficacy", "europepmc", "failed"))
        outcomes.append(outcome("vaccine.cogs", "pubmed", "skipped"))
        runtime = SimpleNamespace(integrations={})
        with mock.patch("services.drafter.retrieval.plan_requests", return_value=["r"] * 5), \
             mock.patch("services.drafter.retrieval.run_requests", return_value=outcomes), \
             mock.patch("services.drafter.retrieval.unconfigured_source_keys", return_value=("who_guidelines",)):
            report = retrieve(["intent"], sources=("pubmed", "europepmc", "fda", "who_guidelines"), runtime=runtime)
        found = report.found
        self.assertEqual([item.url for item in found["vaccine.efficacy"]], ["https://a.org/1"])
        self.assertEqual(sorted(found["vaccine.efficacy"][0].source_lanes), ["europepmc", "pubmed"])
        self.assertEqual(len(found["vaccine.safety"]), 1)
        # A source failed only if every request to it failed; one failed request among
        # successes is that variable's problem, not the source's.
        self.assertEqual(report.failed_sources, ("fda",))
        self.assertEqual(report.unconfigured_sources, ("who_guidelines",))
        self.assertEqual(report.failed_for["vaccine.efficacy"], ("europepmc",))
        self.assertEqual(report.failed_for["vaccine.safety"], ("fda",))
        # The provider's own words travel with the result, so a failure can be diagnosed later.
        self.assertEqual(report.source_errors["fda"], "openFDA returned HTTP 503")
        # A skipped request was never sent: a variable only skipped was never searched.
        self.assertEqual(report.asked, {"vaccine.efficacy": 3, "vaccine.safety": 2})


if __name__ == "__main__":
    unittest.main()
