"""A tool's interface must accept what the pipeline behind it accepts, and no less.

Every drift here was silent, which is why these are tests rather than review notes. An
interface narrower than its pipeline does not fail: it quietly runs a different search,
or parses a file it was never told the format of, and the result looks like an answer.

Three boundaries, one per class of drift found:

    parameter parity   every pipeline parameter is reachable, operational, or derived
    upload parity      the API refuses exactly the formats the parser refuses
    lane reporting     a lane that produced nothing says which kind of nothing it was

The tables below are the point of the file. A new pipeline parameter has to be named in
one of them, so adding one without deciding whether a reader can reach it fails here.
"""

from __future__ import annotations

import dataclasses
import inspect
import pathlib
import unittest
from datetime import datetime, timezone

from services.chunker import run_pipeline as chunker_run_pipeline
from services.searcher import (
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    SearchReport,
    SourceQueryIntent,
    outcomes_to_dicts,
    plan_requests,
    run_pipeline as searcher_run_pipeline,
    source_keys,
    source_specs,
)
from services.searcher.models import Finding, SearchOutcome, SearchRequest

from api.routes import chunker as chunker_route
from api.routes import searcher as searcher_route
from api.uploads import DOCUMENT_FORMAT_HINT, document_upload_parts

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Pipeline parameters a reader is deliberately not given, and why.
#:
#: Budgets, error policy, injected provider capabilities, and progress plumbing. None of
#: them describes the search or the document a reader asked about, so exposing them would
#: put deployment concerns on a page.
OPERATIONAL = {
    "runtime": "injected provider capability",
    "llm_client": "injected provider capability",
    "max_tokens": "token budget, a deployment concern",
    "max_uses": "tool-call budget, a deployment concern",
    "raise_source_errors": "the standalone tool always prefers partial results",
    "progress_callback": "streaming plumbing",
}

#: Pipeline parameters the route supplies from something the reader did give, and from
#: what. Listed rather than assumed, so a parameter cannot become "derived" by omission.
DERIVED = {
    "chunker": {
        "file_path": "the uploaded file, written to a temp path",
        "doc_id": "the uploaded filename's stem",
        "config": "found from org, source_type and intervention_class",
    },
    "searcher": {},
}


def _outcome(source: str, query: str, **kwargs) -> SearchOutcome:
    return SearchOutcome(
        request=SearchRequest(scope_ref="query", source=source, query=query),
        **kwargs,
    )


def _free_text_intent(
    text: str = "resected melanoma",
    entities: tuple[RetrievalEntity, ...] = (),
) -> RetrievalIntent:
    """What the Searcher page sends: prose, and whatever the reader stated."""
    return RetrievalIntent(
        scope_ref="query",
        topic=text,
        description="",
        indication=text,
        intervention_class="",
        entities=entities,
        queries=(SourceQueryIntent(text=text, tracks=("general",)),),
    )


#: Every field of Searcher's input contract, and how the interface accounts for it.
#:
#: Anchored on the model rather than on `run_pipeline`, which is the correction this
#: table exists to make. The first version of these tests compared the route to that
#: function and passed, while the function itself could not express `entities` - so four
#: sources were unreachable, and the page blamed the sources rather than the missing
#: field. A convenience function is a caller like any other. What an adapter can be told
#: is the contract.
#:
#: Three buckets and no fourth: a field is offered, or carried as lineage, or declined
#: for a stated reason. A new field on the model belongs to one of them before it ships.
EXPOSED_AS = {
    "topic": "query",
    "indication": "condition",
    "intervention_class": "intervention",
    "entities": "entities",
    "queries": "query",
    "facets.intervention": "product",
    "facets.population": "population",
    "facets.outcome": "outcome",
}

#: Bookkeeping the caller never states: it identifies a request, it does not shape one.
LINEAGE = {
    "scope_ref": "names the intent, assigned by the caller's own structure",
    "intent_id": "derived from the query's own material",
    "document_refs": "which parsed blocks a query came from, and a free-text query came from none",
    "target_refs": "which quantitative targets a query serves, and this page has no targets",
    "text": "the query itself, already offered as `query`",
}

#: Declined, with the reason. Absent from the interface on purpose, not by omission.
NOT_EXPOSED = {
    "description": "no adapter reads it; Scout passes it for its own prompts",
    "evidence_domain": "the source toggles already choose which lanes run, more directly",
    "tracks": "Scout's multi-angle fan-out over one topic, not a statement about the subject",
    "facets.condition": "every field-addressed source declares condition its anchor, and an anchor always takes the intent's value, so a query-level condition narrows nothing",
}


class InputContractTests(unittest.TestCase):
    """Every field an adapter can be told is offered, carried, or declined by name."""

    def _contract_fields(self) -> set[str]:
        fields = {field.name for field in dataclasses.fields(RetrievalIntent)}
        fields |= {field.name for field in dataclasses.fields(SourceQueryIntent)}
        fields -= {"facets"}
        fields |= {
            f"facets.{field.name}" for field in dataclasses.fields(QueryFacets)
        }
        return fields

    def test_every_contract_field_is_accounted_for(self) -> None:
        accounted = set(EXPOSED_AS) | set(LINEAGE) | set(NOT_EXPOSED)
        unaccounted = sorted(self._contract_fields() - accounted)
        self.assertEqual(
            unaccounted,
            [],
            f"input-contract fields in no bucket: {unaccounted}. Offer them, or add "
            "them to LINEAGE or NOT_EXPOSED with a reason.",
        )

    def test_the_buckets_describe_real_fields(self) -> None:
        """A stale entry would let a real field hide behind a name that no longer exists."""
        accounted = set(EXPOSED_AS) | set(LINEAGE) | set(NOT_EXPOSED)
        self.assertEqual(sorted(accounted - self._contract_fields()), [])

    def test_the_buckets_do_not_overlap(self) -> None:
        buckets = (set(EXPOSED_AS), set(LINEAGE), set(NOT_EXPOSED))
        for first in range(len(buckets)):
            for second in range(first + 1, len(buckets)):
                self.assertEqual(buckets[first] & buckets[second], set())

    def test_everything_exposed_is_reachable_from_the_route(self) -> None:
        accepted = set(inspect.signature(searcher_route.run_searcher).parameters)
        missing = sorted(set(EXPOSED_AS.values()) - accepted)
        self.assertEqual(
            missing, [], f"claimed exposed but the route has no such field: {missing}"
        )

    def test_a_declined_field_has_a_reason(self) -> None:
        for field, reason in NOT_EXPOSED.items():
            with self.subTest(field=field):
                self.assertGreater(len(reason.split()), 4, field)


class ParameterParityTests(unittest.TestCase):
    """Every pipeline parameter is reachable, operational, or derived. No fourth case."""

    def _assert_parity(self, tool: str, pipeline, route) -> None:
        accepted = set(inspect.signature(route).parameters)
        derived = DERIVED[tool]
        unreachable = [
            name
            for name in inspect.signature(pipeline).parameters
            if name not in accepted and name not in OPERATIONAL and name not in derived
        ]
        self.assertEqual(
            unreachable,
            [],
            f"{tool}: pipeline parameters a reader cannot reach: {unreachable}. "
            "Forward them, or name them in OPERATIONAL or DERIVED with a reason.",
        )

    def test_searcher(self) -> None:
        self._assert_parity("searcher", searcher_run_pipeline, searcher_route.run_searcher)

    def test_chunker(self) -> None:
        self._assert_parity("chunker", chunker_run_pipeline, chunker_route.run_chunker)

    def test_operational_parameters_stay_off_every_interface(self) -> None:
        for route in (searcher_route.run_searcher, chunker_route.run_chunker):
            accepted = set(inspect.signature(route).parameters)
            self.assertEqual(accepted & set(OPERATIONAL), set(), route.__name__)

    def test_searcher_forwards_every_slot_of_the_one_request(self) -> None:
        """Named outright, so deleting any slot's wiring fails here, not in a run.

        The four slots an adapter unpacks its own part of. A page offering three of them
        cannot reach the sources that read the fourth, and the missing field looked like
        a property of those sources instead of a hole in the form.
        """
        accepted = set(inspect.signature(searcher_route.run_searcher).parameters)
        self.assertLessEqual(
            {"query", "sources", "condition", "intervention", "entities"}, accepted
        )


class UploadParityTests(unittest.TestCase):
    """The API refuses what the parser refuses, before a stream opens."""

    #: Every route that takes a document upload. All of them go through one guard.
    DOCUMENT_ROUTES = ("chunker", "inspector", "scout", "aligner", "expert")

    def test_supported_formats_are_accepted(self) -> None:
        self.assertEqual(
            document_upload_parts("Target Profile.docx", tool="Chunker"),
            ("Target Profile", ".docx"),
        )
        self.assertEqual(
            document_upload_parts("Deck.PPTX", tool="Chunker"), ("Deck", ".pptx")
        )

    def test_unsupported_format_is_refused_with_the_shared_hint(self) -> None:
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as caught:
            document_upload_parts("report.pdf", tool="Chunker")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn(DOCUMENT_FORMAT_HINT, caught.exception.detail)

    def test_a_file_with_no_extension_is_refused_not_assumed(self) -> None:
        """The regression this replaced: `suffix or ".docx"` guessed a format.

        A guess is worse than a refusal here. The parser was handed a file it had been
        told was a DOCX, so the reader got python-docx's opinion of a non-zip file
        instead of being told the upload never stated its format.
        """
        from fastapi import HTTPException

        for name in (None, "", "report", "report."):
            with self.subTest(name=name), self.assertRaises(HTTPException):
                document_upload_parts(name, tool="Chunker")

    def test_no_route_derives_a_suffix_of_its_own(self) -> None:
        for name in self.DOCUMENT_ROUTES:
            source = (REPO / "api" / "routes" / f"{name}.py").read_text()
            with self.subTest(route=name):
                self.assertIn("document_upload_parts", source)
                # The exact shape of the old bug, and of any re-introduction of it.
                self.assertNotIn('.suffix or "', source)

    def test_no_route_spells_the_accepted_formats_itself(self) -> None:
        """Two routes had the list in prose, so changing the set would have left them."""
        for name in self.DOCUMENT_ROUTES:
            source = (REPO / "api" / "routes" / f"{name}.py").read_text()
            with self.subTest(route=name):
                self.assertNotIn("DOCX and PPTX", source)


class LaneReportingTests(unittest.TestCase):
    """A lane that produced nothing has to say which kind of nothing it was."""

    def test_report_carries_findings_and_outcomes_together(self) -> None:
        report = SearchReport()
        self.assertEqual(report.findings, [])
        self.assertEqual(report.outcomes, [])

    def test_empty_skipped_and_failed_stay_distinct(self) -> None:
        rows = outcomes_to_dicts(
            [
                _outcome("pubmed", "melanoma AND vaccine"),
                _outcome("ctis", "condition:melanoma", status="skipped"),
                _outcome("chembl", "condition:melanoma", status="failed", error="429"),
            ]
        )
        self.assertEqual(
            [(row["source"], row["status"], row["returned"]) for row in rows],
            [("pubmed", "complete", 0), ("ctis", "skipped", 0), ("chembl", "failed", 0)],
        )
        self.assertEqual(rows[2]["detail"], "429")

    def test_reported_query_is_the_native_one(self) -> None:
        """The point of reporting it: the provider's request, not the reader's sentence."""
        rows = outcomes_to_dicts([_outcome("clinicaltrials", "condition:melanoma")])
        self.assertEqual(rows[0]["query"], "condition:melanoma")

    def test_returned_counts_the_request_not_the_deduped_union(self) -> None:
        found = Finding(
            url="https://example.org/a",
            title="A",
            query="q",
            retrieved_at=datetime.now(timezone.utc),
        )
        rows = outcomes_to_dicts(
            [_outcome("web", "q", findings=[found]), _outcome("pubmed", "q", findings=[found])]
        )
        # Both lanes did return it. Deduplication is what the findings list owns.
        self.assertEqual([row["returned"] for row in rows], [1, 1])


class StatedEntityTests(unittest.TestCase):
    """A named subject reaches the sources that address their API by one."""

    def test_a_stated_entity_makes_its_sources_plannable(self) -> None:
        stated = (
            RetrievalEntity(name="BRAF", entity_type="gene"),
            RetrievalEntity(name="pembrolizumab", entity_type="drug"),
        )
        for key in ("open_targets", "chembl", "uniprot", "fda_safety"):
            with self.subTest(source=key):
                requests = plan_requests(
                    [_free_text_intent(entities=stated)], sources=(key,)
                )
                self.assertTrue(requests)
                for request in requests:
                    self.assertEqual(request.applicability, "applicable")
                    self.assertTrue(request.query, "a plannable lane must ask something")

    def test_class_and_product_are_different_values_doing_different_work(self) -> None:
        """The correction: `facets.intervention` was declined as a duplicate of scope.

        At intent scope the value is the class Scout carries from its run header. The
        facet is one named product, and `facet_groups` adds it as a second request beside
        the scope request rather than replacing it. Calling them the same thing left the
        page able to send only one, so a product-level registry query was unreachable.
        """
        intent = RetrievalIntent(
            scope_ref="q",
            topic="melanoma",
            description="",
            indication="melanoma",
            intervention_class="vaccine",
            queries=(
                SourceQueryIntent(
                    text="melanoma",
                    tracks=("general",),
                    facets=QueryFacets(intervention="intismeran autogene"),
                ),
            ),
        )
        asked = [
            request.query
            for request in plan_requests([intent], sources=("clinicaltrials",))
        ]
        self.assertEqual(
            asked,
            [
                "condition:melanoma AND intervention:vaccine",
                "condition:melanoma AND intervention:intismeran autogene",
            ],
        )

    def test_the_stated_name_reaches_the_native_query(self) -> None:
        """Not merely accepted: the subject has to appear in what the provider receives."""
        stated = (RetrievalEntity(name="BRAF", entity_type="gene"),)
        (request,) = plan_requests(
            [_free_text_intent(entities=stated)], sources=("open_targets",)
        )
        self.assertIn("BRAF", request.query)

    def test_route_refuses_an_entity_whose_type_is_unknown(self) -> None:
        """Dropping it silently would leave the source skipped and the reader unaware."""
        from api.routes.searcher import _parse_entities

        self.assertEqual(
            _parse_entities("BRAF:gene"),
            (RetrievalEntity(name="BRAF", entity_type="gene"),),
        )
        for bad in ("BRAF", "BRAF:widget", ":gene"):
            with self.subTest(raw=bad), self.assertRaises(ValueError):
                _parse_entities(bad)


class FreeTextApplicabilityTests(unittest.TestCase):
    """A source needing a subject the request never named is ruled out, not crashed into."""

    def _entity_sources(self) -> list[str]:
        return [spec.key for spec in source_specs() if spec.required_entity_types]

    def test_there_is_something_to_test(self) -> None:
        """Guards the tests below from passing because the registry changed shape."""
        self.assertNotEqual(self._entity_sources(), [])

    def test_planning_every_source_from_free_text_does_not_raise(self) -> None:
        """The regression: one such source failed the whole run, every lane with it."""
        requests = plan_requests([_free_text_intent()], sources=source_keys())
        self.assertEqual(len(requests), len(source_keys()))

    def test_an_entity_source_is_skipped_with_its_reason(self) -> None:
        for key in self._entity_sources():
            with self.subTest(source=key):
                (request,) = plan_requests([_free_text_intent()], sources=(key,))
                self.assertEqual(request.applicability, "not_applicable")
                self.assertIn("entity", request.applicability_reason)

    def test_a_skip_reason_reaches_the_reader(self) -> None:
        """A reason held on the request and reported from the outcome is not reported."""
        (request,) = plan_requests([_free_text_intent()], sources=("open_targets",))
        (row,) = outcomes_to_dicts([SearchOutcome(request=request, status="skipped")])
        self.assertEqual(row["status"], "skipped")
        self.assertTrue(row["detail"], "a skipped lane with no reason is unreadable")

    def test_a_stated_domain_still_filters_by_domain(self) -> None:
        """Moving the entity check out of the gate must not disable the domain check."""
        intent = RetrievalIntent(
            scope_ref="query",
            topic="efficacy",
            description="",
            indication="malaria",
            intervention_class="vaccine",
            evidence_domain="manufacturing",
            queries=(SourceQueryIntent(text="efficacy", tracks=("general",)),),
        )
        (request,) = plan_requests([intent], sources=("clinicaltrials",))
        self.assertEqual(request.applicability, "not_applicable")
        self.assertIn("evidence domain", request.applicability_reason)


if __name__ == "__main__":
    unittest.main()
