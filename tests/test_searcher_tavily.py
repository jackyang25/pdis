"""The Tavily lane, and the wiring it has to match.

Added beside `web` rather than instead of it, so one document can be read both ways and
compared. `web` asks a model a question and keeps the URLs it cites; this asks a search API and
keeps the page's own text.

Most of these tests are about the seam rather than the search: a source that plans the wrong
shape, or reads a connector the boundary never builds, fails at run time on a real document
and nowhere earlier.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from services.searcher.connectors.tavily import (
    DEFAULT_BASE_URL,
    DEFAULT_SEARCH_DEPTH,
    TavilyHTTPConnector,
)
from services.searcher.controller import (
    SOURCE_REGISTRY,
    plan_requests,
    unconfigured_source_keys,
)
from services.searcher.models import (
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceQueryIntent,
)
from services.scout.stages.conformity import (
    CALIBRATION_EVIDENCE_CLASSES,
    _may_supply_a_measurement,
)
from services.searcher.sources.tavily import (
    MAX_EXCERPT_CHARS,
    MAX_RESULTS,
    TAVILY_INTEGRATION,
    TavilySource,
)


class _FakeConnector:
    """Records what it was asked, returns what it was given."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, int | None]] = []

    def search(self, query, *, max_results=None):
        self.calls.append((query, max_results))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def intent(*queries: str) -> RetrievalIntent:
    return RetrievalIntent(
        scope_ref="drug.efficacy",
        topic="efficacy",
        description="Primary efficacy endpoints.",
        indication="tuberculosis",
        intervention_class="drug",
        evidence_domain="clinical",
        queries=tuple(
            SourceQueryIntent(text=text, tracks=("general",)) for text in queries
        ),
    )


def runtime(connector) -> SearchRuntime:
    return SearchRuntime(llm_client=None, integrations={TAVILY_INTEGRATION: connector})


def request(query: str = "tuberculosis long-acting injectable") -> SearchRequest:
    return SearchRequest(scope_ref="drug.efficacy", source="tavily", query=query)


class RegistrationTests(unittest.TestCase):
    def test_the_source_is_registered_under_its_key(self):
        self.assertIn("tavily", SOURCE_REGISTRY)
        self.assertIs(type(SOURCE_REGISTRY["tavily"]), TavilySource)

    def test_it_declares_its_integration_so_it_can_disable_itself(self):
        """Without this the lane fails every request instead of standing down.

        `unconfigured_source_keys` reads `integration_key`, so a source that omits it is
        selected even when its connector was never built.
        """
        self.assertEqual(SOURCE_REGISTRY["tavily"].spec.integration_key, TAVILY_INTEGRATION)
        self.assertEqual(
            unconfigured_source_keys(["tavily"], SearchRuntime(llm_client=None)),
            ("tavily",),
        )
        self.assertEqual(
            unconfigured_source_keys(["tavily"], runtime(_FakeConnector({"results": []}))),
            (),
        )

    def test_it_serves_every_field_like_the_lane_it_is_compared_against(self):
        """A domain gate would make it answer a different question from `web`."""
        self.assertEqual(SOURCE_REGISTRY["tavily"].spec.evidence_domains, ())
        self.assertEqual(SOURCE_REGISTRY["web"].spec.evidence_domains, ())

    def test_it_is_throttled_like_the_lane_it_is_compared_against(self):
        """Otherwise a comparison run also compares concurrency."""
        self.assertEqual(
            SOURCE_REGISTRY["tavily"].spec.worker_limit,
            SOURCE_REGISTRY["web"].spec.worker_limit,
        )

    def test_it_requires_no_entity(self):
        """`web` requires none, so gating this one would change what is being compared."""
        self.assertEqual(SOURCE_REGISTRY["tavily"].spec.required_entity_types, ())


class PlanningTests(unittest.TestCase):
    def test_one_request_per_query_with_the_text_untouched(self):
        """The queries are already keyword-shaped, so nothing is rewritten for a search API."""
        planned = TavilySource().plan(intent("a query", "another query"))
        self.assertEqual([r.query for r in planned], ["a query", "another query"])

    def test_planning_matches_the_lane_it_replaces(self):
        """Same count, same text, same tracks. A difference here would confound the result."""
        given = intent("one", "two", "three")
        mine = TavilySource().plan(given)
        theirs = SOURCE_REGISTRY["web"].plan(given)
        self.assertEqual([r.query for r in mine], [r.query for r in theirs])
        self.assertEqual([r.tracks for r in mine], [r.tracks for r in theirs])

    def test_lineage_is_carried_so_a_finding_can_be_traced_to_its_intent(self):
        planned = TavilySource().plan(intent("a query"))
        self.assertEqual(len(planned[0].intent_ids), len(planned[0].input_queries))
        self.assertTrue(planned[0].intent_ids)

    def test_the_controller_plans_it_without_special_casing(self):
        planned = plan_requests([intent("a query")], sources=["tavily"])
        self.assertEqual([r.source for r in planned], ["tavily"])


class SearchTests(unittest.TestCase):
    def test_a_result_becomes_a_finding_carrying_the_page_text(self):
        """The point of the lane. `web` yields the model's sentence about the page instead."""
        connector = _FakeConnector({
            "results": [{
                "url": "https://who.int/tb",
                "title": "WHO TB guidance",
                "content": "Treatment  should   continue for six months.",
            }]
        })
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].url, "https://who.int/tb")
        self.assertEqual(findings[0].title, "WHO TB guidance")
        # Whitespace normalised, words untouched.
        self.assertEqual(findings[0].excerpt, "Treatment should continue for six months.")
        self.assertEqual(findings[0].source, "tavily")
        self.assertEqual(findings[0].query, request().query)

    def test_the_fuller_text_is_preferred_when_present(self):
        """A longer passage is likelier to contain the sentence a number sits in."""
        connector = _FakeConnector({
            "results": [{
                "url": "https://who.int/tb",
                "content": "short",
                "raw_content": "the fuller extracted page text",
            }]
        })
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertEqual(findings[0].excerpt, "the fuller extracted page text")

    def test_a_long_passage_is_truncated_rather_than_dropped(self):
        connector = _FakeConnector({
            "results": [{"url": "https://a.test", "content": "x" * (MAX_EXCERPT_CHARS + 500)}]
        })
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertTrue(findings[0].excerpt.endswith("..."))
        self.assertLessEqual(len(findings[0].excerpt), MAX_EXCERPT_CHARS + 3)

    def test_no_extractable_text_yields_no_excerpt_rather_than_an_empty_one(self):
        """`Finding.excerpt` is absent-or-a-passage.

        An empty string downstream reads as a source that stated nothing, which is a different
        fact from a page whose text could not be extracted.
        """
        connector = _FakeConnector({"results": [{"url": "https://a.test", "title": "A"}]})
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertIsNone(findings[0].excerpt)

    def test_a_record_with_no_url_is_skipped(self):
        """A finding is identified by its URL, so one without is not a finding."""
        connector = _FakeConnector({
            "results": [{"title": "no url"}, {"url": "https://a.test", "title": "A"}]
        })
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertEqual([f.url for f in findings], ["https://a.test"])

    def test_a_missing_title_falls_back_to_the_url_never_to_a_generated_one(self):
        connector = _FakeConnector({"results": [{"url": "https://a.test"}]})
        findings = TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertEqual(findings[0].title, "https://a.test")

    def test_the_declared_result_cap_is_what_is_asked_for(self):
        """So the spec's number and the request's number cannot disagree."""
        connector = _FakeConnector({"results": []})
        TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertEqual(connector.calls, [(request().query, MAX_RESULTS)])

    def test_generation_bounds_are_ignored_rather_than_reinterpreted(self):
        """`max_tokens` and `max_uses` bound a model, not a search API.

        Turning them into a result limit would silently disagree with the cap the spec
        declares, which is the kind of difference nobody finds until they compare counts.
        """
        connector = _FakeConnector({"results": []})
        TavilySource().search(request(), runtime(connector), max_tokens=99, max_uses=99)
        self.assertEqual(connector.calls[0][1], MAX_RESULTS)

    def test_an_absent_connector_is_a_stated_failure(self):
        with self.assertRaises(RuntimeError) as raised:
            TavilySource().search(
                request(), SearchRuntime(llm_client=None), max_tokens=1, max_uses=1
            )
        self.assertIn("not configured", str(raised.exception))

    def test_an_error_in_the_body_is_a_failure_not_an_empty_result(self):
        """Tavily reports failure in a 200 body.

        Returning no findings would record the search as having run and found nothing, which
        is a different fact from a search that failed.
        """
        connector = _FakeConnector({"error": "rate limited"})
        with self.assertRaises(RuntimeError) as raised:
            TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1)
        self.assertIn("rate limited", str(raised.exception))

    def test_an_unexpected_shape_is_a_failure(self):
        for shape in ([], "text", None, {"data": []}):
            with self.subTest(shape=shape):
                with self.assertRaises(RuntimeError):
                    TavilySource().search(
                        request(), runtime(_FakeConnector(shape)), max_tokens=1, max_uses=1
                    )

    def test_a_search_that_genuinely_returns_nothing_is_not_a_failure(self):
        connector = _FakeConnector({"results": []})
        self.assertEqual(
            TavilySource().search(request(), runtime(connector), max_tokens=1, max_uses=1), []
        )


class ConnectorTests(unittest.TestCase):
    def test_it_refuses_to_be_built_without_a_key(self):
        with self.assertRaises(ValueError):
            TavilyHTTPConnector(api_key="   ")

    def test_it_refuses_an_unknown_depth(self):
        """Two values, and a typo would otherwise be sent to the provider verbatim."""
        with self.assertRaises(ValueError):
            TavilyHTTPConnector(api_key="k", search_depth="deep")

    def test_it_refuses_a_relative_base_url(self):
        with self.assertRaises(ValueError):
            TavilyHTTPConnector(api_key="k", base_url="api.tavily.com")

    def test_it_refuses_a_non_positive_timeout_or_cap(self):
        with self.assertRaises(ValueError):
            TavilyHTTPConnector(api_key="k", timeout_seconds=0)
        with self.assertRaises(ValueError):
            TavilyHTTPConnector(api_key="k", max_results=0)

    def test_the_key_travels_in_a_header_never_in_the_payload(self):
        """A logged request body must not be able to leak the credential."""
        captured = {}

        class _Response:
            def read(self):
                return json.dumps({"results": []}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode())
            return _Response()

        with patch("services.searcher.connectors.tavily.urlopen", fake_urlopen):
            TavilyHTTPConnector(api_key="secret-key").search("a query")

        self.assertEqual(captured["headers"].get("Authorization"), "Bearer secret-key")
        self.assertNotIn("secret-key", json.dumps(captured["body"]))

    def test_it_asks_for_neither_a_generated_answer_nor_a_summary(self):
        """A model's answer about the results is exactly what this lane exists to avoid."""
        captured = {}

        class _Response:
            def read(self):
                return json.dumps({"results": []}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured.update(json.loads(req.data.decode()))
            return _Response()

        with patch("services.searcher.connectors.tavily.urlopen", fake_urlopen):
            TavilyHTTPConnector(api_key="k").search("a query", max_results=4)

        self.assertIs(captured["include_answer"], False)
        self.assertEqual(captured["query"], "a query")
        self.assertEqual(captured["max_results"], 4)
        self.assertEqual(captured["search_depth"], DEFAULT_SEARCH_DEPTH)

    def test_invalid_json_is_a_stated_failure(self):
        class _Response:
            def read(self):
                return b"not json"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with patch("services.searcher.connectors.tavily.urlopen", lambda *a, **k: _Response()):
            with self.assertRaises(RuntimeError) as raised:
                TavilyHTTPConnector(api_key="k").search("a query")
        self.assertIn("invalid JSON", str(raised.exception))


class BoundaryWiringTests(unittest.TestCase):
    """The connector is only ever built at the application boundary."""

    def test_no_key_means_no_integration_and_so_no_lane(self):
        from api.deps import get_search_integrations

        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            self.assertNotIn(TAVILY_INTEGRATION, get_search_integrations())

    def test_a_key_builds_the_connector_with_the_declared_defaults(self):
        from api.deps import get_search_integrations

        with patch.dict(
            os.environ,
            {"TAVILY_API_KEY": "k", "TAVILY_BASE_URL": "", "TAVILY_SEARCH_DEPTH": ""},
            clear=False,
        ):
            built = get_search_integrations()[TAVILY_INTEGRATION]
        self.assertEqual(built.base_url, DEFAULT_BASE_URL)
        self.assertEqual(built.search_depth, DEFAULT_SEARCH_DEPTH)

    def test_the_depth_can_be_lowered_for_a_cheaper_run(self):
        from api.deps import get_search_integrations

        with patch.dict(os.environ, {"TAVILY_API_KEY": "k", "TAVILY_SEARCH_DEPTH": "basic"}):
            self.assertEqual(
                get_search_integrations()[TAVILY_INTEGRATION].search_depth, "basic"
            )

    def test_the_deploy_declares_the_key_without_committing_it(self):
        import pathlib

        render = pathlib.Path("render.yaml").read_text()
        self.assertIn("TAVILY_API_KEY", render)
        # `sync: false` is what keeps it out of the repository.
        block = render[render.index("TAVILY_API_KEY"):]
        self.assertIn("sync: false", block[:120])


if __name__ == "__main__":
    unittest.main()


class WhichSourcesMaySupplyANumberTests(unittest.TestCase):
    """Two questions, one decision, one place.

    `conformity` decided this with `(finding.excerpt_source_lane or finding.source) != "web"`.
    That asked whether the excerpt was the source's own words, and hid a second question it
    never asked: whether the source is one a number should rest on.

    Measured on a real run, six lanes were eligible under the old rule and only the two
    literature lanes ever produced a candidate. So the rule was already "peer-reviewed and
    equivalent" in practice, by accident of which excerpts contain comparable numbers. Adding a
    general web lane is what made that unsafe: Tavily's excerpt *is* the page's own words, so a
    blog accurately quoted would have entered the arithmetic looking like a phase III result.
    """

    def _finding(self, lane: str):
        from datetime import datetime, timezone

        from services.searcher.models import Finding

        return Finding(
            url="https://a.test",
            title="A",
            query="q",
            retrieved_at=datetime.now(timezone.utc),
            source=lane,
        )

    def test_the_eligible_classes_are_named_against_the_closed_set(self):
        """No new field and nothing new to keep in step.

        Every source already declares an `evidence_class`, already validated against
        `EVIDENCE_CLASSES`, so the rule is expressed in vocabulary that exists.
        """
        from shared.vocabulary import EVIDENCE_CLASSES

        self.assertEqual(CALIBRATION_EVIDENCE_CLASSES, {"literature", "registry", "regulatory"})
        self.assertLessEqual(CALIBRATION_EVIDENCE_CLASSES, EVIDENCE_CLASSES)

    def test_literature_registries_and_regulators_may_supply_a_number(self):
        for lane in ("pubmed", "semantic_scholar", "europepmc", "clinicaltrials", "isrctn", "ctis", "fda", "fda_safety"):
            with self.subTest(lane=lane):
                self.assertTrue(_may_supply_a_measurement(self._finding(lane)))

    def test_a_general_web_lane_may_not(self):
        """The reason this rule is now explicit.

        `web` fails on both counts and `tavily` on authority alone, which is the case the old
        rule would have admitted.
        """
        self.assertFalse(_may_supply_a_measurement(self._finding("web")))
        self.assertFalse(_may_supply_a_measurement(self._finding("tavily")))

    def test_a_curated_database_a_guideline_and_a_statistic_may_not(self):
        """Not because they are untrustworthy.

        A number taken from them is a number whose provenance a reviewer would question, and
        none of them produced a candidate on a real run in any case.
        """
        for lane in ("chembl", "open_targets", "who_guidelines"):
            with self.subTest(lane=lane):
                self.assertFalse(_may_supply_a_measurement(self._finding(lane)))

    def test_an_unknown_lane_is_refused_rather_than_trusted(self):
        """The one place the old behaviour is deliberately reversed.

        It trusted anything that was not the string `"web"`, so a lane renamed or removed since
        a result was saved supplied measurements on the strength of not being one string.
        """
        self.assertFalse(_may_supply_a_measurement(self._finding("a_lane_that_was_removed")))

    def test_both_questions_are_asked_even_though_one_subsumes_the_other_today(self):
        """They are not the same property.

        Only `general` lanes fail the verbatim test today, and `general` is not eligible
        anyway. A literature lane that summarised rather than extracted would pass on
        authority and fail on fidelity, which is the case the first question exists for.
        """
        self.assertFalse(SOURCE_REGISTRY["web"].spec.excerpt_is_verbatim)
        self.assertTrue(SOURCE_REGISTRY["tavily"].spec.excerpt_is_verbatim)
        generated = {
            key for key, adapter in SOURCE_REGISTRY.items()
            if not adapter.spec.excerpt_is_verbatim
        }
        self.assertEqual(generated, {"web"}, "a new generated-excerpt lane did not say so")

    def test_the_whole_table_is_visible_here(self):
        """Every lane and its verdict, so the effect of the rule is readable in one place."""
        verdicts = {
            key: _may_supply_a_measurement(self._finding(key)) for key in SOURCE_REGISTRY
        }
        self.assertEqual(
            {key for key, allowed in verdicts.items() if allowed},
            {"pubmed", "semantic_scholar", "europepmc", "clinicaltrials", "isrctn", "ctis", "fda", "fda_safety"},
        )


if __name__ == "__main__":
    unittest.main()
