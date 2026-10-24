"""A whole Drafter run, with a scripted model and scripted retrieval."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

import httpx
import openai

from services.drafter import run_pipeline, validate_result_contract
from services.drafter.retrieval import RetrievalReport
from services.searcher import Finding
from shared.ai import ResponseTruncatedError
from shared.vocabulary import attribute_definitions
from tests.drafter_support import StageClient, variable_in

VARIABLES = [definition.name for definition in attribute_definitions("vaccine")]
EXCERPT = "RTS,S efficacy against clinical malaria was 56% over 12 months."


def finding(url: str) -> Finding:
    return Finding(url=url, title="RTS,S phase 3", query="q", retrieved_at=datetime.now(timezone.utc),
                   excerpt=EXCERPT, source="pubmed", source_lanes=["pubmed"], excerpt_source_lane="pubmed")


def plan(message: str) -> dict:
    return {"queries": [{"query": f"{variable_in(message)} malaria vaccine", "purpose": "comparable",
                         "facets": {"condition": "", "intervention": "", "population": "", "outcome": ""}}]}


EVIDENCE = {"observations": [{"basis": "comparable_product", "product": "RTS,S", "measure": "efficacy",
                              "quote": "efficacy against clinical malaria was 56%", "value": 56, "lower": None, "upper": None, "unit": "%",
                              "value_text": "56%"}]}


def suggestion(message: str) -> dict:
    observation = next(line for line in message.splitlines() if line.startswith("[")).split("]")[0][1:]
    return {"suggestion": {"kind": "range", "minimum": "50%", "preferred": "75%", "statement": "",
                           "rationale": "Comparable vaccines reached 56%.", "basis_ids": [observation]}}


def found_for_every_variable(intents, **kwargs):
    return RetrievalReport(
        found={intent.scope_ref: [finding(f"https://pubmed.org/{index}")] for index, intent in enumerate(intents)},
        failed_sources=("fda",), unconfigured_sources=("who_guidelines",), failed_for={},
        source_errors={"fda": "openFDA returned HTTP 503"}, asked={intent.scope_ref: 2 for intent in intents},
    )


def nothing_found(intents, **kwargs):
    return RetrievalReport({}, (), (), {}, {}, asked={intent.scope_ref: 1 for intent in intents})


class PipelineTests(unittest.TestCase):
    def run_drafter(self, client, *, retrieved=found_for_every_variable):
        events = []
        with mock.patch("services.drafter.pipeline.retrieve", side_effect=retrieved) as retrieve:
            result = run_pipeline(
                org="bmgf", intervention_class="vaccine", indication="malaria", llm_client=client, runtime=object(),
                progress_callback=lambda stage, completed=None, total=None: events.append(stage),
            )
        return result, events, retrieve

    def test_without_a_draft_every_variable_is_suggested_and_the_result_holds(self):
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=suggestion)
        result, events, _ = self.run_drafter(client)
        value = result.to_dict()
        validate_result_contract(value)
        self.assertEqual([variable["name"] for variable in value["variables"]], VARIABLES)
        self.assertTrue(all(variable["status"] == "complete" for variable in value["variables"]))
        efficacy = value["variables"][VARIABLES.index("vaccine.efficacy")]
        self.assertEqual(efficacy["observations"][0]["id"], "vaccine.efficacy:o1")
        self.assertEqual(value["failed_sources"], ["fda"])
        self.assertEqual(value["unconfigured_sources"], ["who_guidelines"])
        self.assertEqual(value["source_errors"], [{"source": "fda", "message": "openFDA returned HTTP 503"}])
        self.assertEqual(client.count("drafter_search_plan"), len(VARIABLES))
        self.assertEqual(list(dict.fromkeys(events)), ["plan", "search", "evidence", "suggest"])
        # Planning and reading copy and phrase, so they run on the fast tier; the
        # suggestion weighs the evidence, so it does not.
        self.assertEqual(client.tasks, {
            "drafter_search_plan": {"fast"}, "drafter_evidence_reading": {"fast"}, "drafter_suggestion": {"reasoning"},
        })

    def test_every_fan_out_reports_a_count_that_rises_to_its_total(self):
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=suggestion)
        counts = []
        with mock.patch("services.drafter.pipeline.retrieve", side_effect=found_for_every_variable):
            run_pipeline(
                org="bmgf", intervention_class="vaccine", indication="malaria", llm_client=client, runtime=object(),
                progress_callback=lambda stage, completed=None, total=None: counts.append((stage, completed, total)),
            )
        for stage in ("plan", "evidence", "suggest"):
            seen = [(done, total) for name, done, total in counts if name == stage]
            self.assertEqual(seen, [(done, len(VARIABLES)) for done in range(len(VARIABLES) + 1)])

    def test_one_variable_failing_leaves_the_others_complete(self):
        def flaky_suggestion(message):
            return None if variable_in(message) == "vaccine.efficacy" else suggestion(message)

        def flaky_plan(message):
            return {"queries": []} if variable_in(message) == "vaccine.safety" else plan(message)

        client = StageClient(drafter_search_plan=flaky_plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=flaky_suggestion)
        result, _, _ = self.run_drafter(client)
        value = validate_result_contract(result.to_dict())
        by_name = {variable["name"]: variable for variable in value["variables"]}
        self.assertEqual(by_name["vaccine.efficacy"]["failure"]["code"], "suggestion_failed")
        self.assertEqual(by_name["vaccine.safety"]["failure"]["code"], "search_planning_failed")
        self.assertEqual(by_name["vaccine.dose_volume"]["status"], "complete")

    def test_a_provider_error_costs_one_reading_or_one_variable_never_the_run(self):
        # A reply cut off at its token limit, or the provider unreachable, raises from the client.
        def unreachable(detail):
            return openai.APIConnectionError(message=detail, request=httpx.Request("POST", "https://x"))

        def evidence(message):
            if variable_in(message) == "vaccine.efficacy":
                raise ResponseTruncatedError("The model reached the response limit before completing its answer.")
            return EVIDENCE

        def flaky_suggestion(message):
            if variable_in(message) == "vaccine.safety":
                raise unreachable("rate limited")
            return suggestion(message)

        def flaky_plan(message):
            if variable_in(message) == "vaccine.cogs":
                raise unreachable("connection reset")
            return plan(message)

        client = StageClient(drafter_search_plan=flaky_plan, drafter_evidence_reading=evidence, drafter_suggestion=flaky_suggestion)
        result, _, _ = self.run_drafter(client)
        by_name = {variable["name"]: variable for variable in validate_result_contract(result.to_dict())["variables"]}
        self.assertEqual(by_name["vaccine.efficacy"]["unread_findings"], 1)
        self.assertEqual(by_name["vaccine.safety"]["failure"]["code"], "suggestion_failed")
        self.assertEqual(by_name["vaccine.safety"]["failure"]["cause"], "provider_error")
        self.assertIn("rate limited", by_name["vaccine.safety"]["failure"]["message"])
        self.assertEqual(by_name["vaccine.cogs"]["failure"]["code"], "search_planning_failed")
        self.assertEqual(by_name["vaccine.dose_volume"]["status"], "complete")

    def test_a_reply_cut_off_twice_records_its_cause(self):
        cut_off = ResponseTruncatedError("The model reached the response limit.")
        def flaky_suggestion(message):
            return cut_off if variable_in(message) == "vaccine.safety" else suggestion(message)

        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=flaky_suggestion)
        result, _, _ = self.run_drafter(client)
        failure = next(variable for variable in validate_result_contract(result.to_dict())["variables"]
                       if variable["name"] == "vaccine.safety")["failure"]
        self.assertEqual((failure["code"], failure["cause"]), ("suggestion_failed", "response_truncated"))

    def test_a_programming_error_stops_the_run_rather_than_costing_one_variable(self):
        def broken(message):
            raise TypeError("a bug")

        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=broken, drafter_suggestion=suggestion)
        with self.assertRaises(TypeError):
            self.run_drafter(client)

    def test_quotes_no_source_contains_leave_the_variable_without_evidence(self):
        misquoted = {"observations": [{**EVIDENCE["observations"][0], "quote": "efficacy was 90%"}]}
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=misquoted, drafter_suggestion=suggestion)
        result, _, _ = self.run_drafter(client)
        efficacy = next(variable for variable in validate_result_contract(result.to_dict())["variables"]
                        if variable["name"] == "vaccine.efficacy")
        self.assertEqual(efficacy["status"], "failed")
        self.assertEqual(efficacy["failure"]["code"], "evidence_unavailable")
        self.assertIsNone(efficacy["failure"]["cause"])
        self.assertIn("quotes", efficacy["failure"]["message"])
        self.assertEqual(efficacy["unverified_quotes"], 1)
        self.assertEqual(client.count("drafter_suggestion"), 0)

    def test_a_variable_no_source_was_asked_about_is_not_insufficient(self):
        # Every source unconfigured or inapplicable: nothing could have answered, so
        # "insufficient evidence" would describe a search that never happened.
        never_asked = lambda intents, **kwargs: RetrievalReport({}, (), ("pubmed",), {}, {}, asked={})
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=suggestion)
        result, _, _ = self.run_drafter(client, retrieved=never_asked)
        value = validate_result_contract(result.to_dict())
        self.assertTrue(all(variable["failure"]["code"] == "evidence_unavailable" for variable in value["variables"]))
        self.assertIn("pubmed", value["variables"][0]["failure"]["message"])

    def test_a_source_that_returns_nothing_leaves_the_variable_insufficient(self):
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=suggestion)
        result, _, _ = self.run_drafter(client, retrieved=nothing_found)
        value = validate_result_contract(result.to_dict())
        self.assertTrue(all(variable["suggestion"]["kind"] == "insufficient" for variable in value["variables"]))
        self.assertEqual(client.count("drafter_suggestion"), 0)

    def test_no_evidence_because_sources_failed_is_a_failure_not_an_outcome(self):
        # "Not enough evidence" is a reading of evidence; when nothing could be read because
        # the sources failed, saying so would report a pipeline failure as a finding.
        failed_everywhere = lambda intents, **kwargs: RetrievalReport(
            found={}, failed_sources=("pubmed",), unconfigured_sources=(),
            failed_for={intent.scope_ref: ("pubmed",) for intent in intents}, source_errors={"pubmed": "timed out"},
            asked={intent.scope_ref: 1 for intent in intents},
        )
        client = StageClient(drafter_search_plan=plan, drafter_evidence_reading=EVIDENCE, drafter_suggestion=suggestion)
        result, _, _ = self.run_drafter(client, retrieved=failed_everywhere)
        value = validate_result_contract(result.to_dict())
        efficacy = next(variable for variable in value["variables"] if variable["name"] == "vaccine.efficacy")
        self.assertEqual(efficacy["status"], "failed")
        self.assertEqual(efficacy["failure"]["code"], "evidence_unavailable")
        self.assertIn("pubmed", efficacy["failure"]["message"])

    def test_an_unknown_disease_is_refused_before_any_work(self):
        with self.assertRaises(ValueError):
            run_pipeline(org="bmgf", intervention_class="vaccine", indication="not_a_disease",
                         llm_client=StageClient(), runtime=object())

    def test_an_unknown_product_type_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            run_pipeline(org="bmgf", intervention_class="widget", indication="malaria",
                         llm_client=StageClient(), runtime=object())


if __name__ == "__main__":
    unittest.main()
