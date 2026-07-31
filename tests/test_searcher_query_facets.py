"""One upstream layer states query meaning; adapters translate but never infer.

Scout's query generation already knows the condition, intervention, population,
and outcome behind each query. These tests hold that structure on the intent so
source adapters select the fields their grammar needs instead of recovering
meaning from prose.
"""

from __future__ import annotations

import unittest

from services.searcher import (
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    SourceQueryIntent,
)
from services.searcher.sources.clinicaltrials import ClinicalTrialsSource
from services.searcher.sources.literature import (
    build_pubmed_query,
    build_semantic_scholar_query,
)


def _intent(*queries: SourceQueryIntent) -> RetrievalIntent:
    return RetrievalIntent(
        scope_ref="vaccine.efficacy",
        topic="efficacy",
        description="Vaccine efficacy against infection.",
        indication="malaria",
        intervention_class="vaccine",
        entities=(
            RetrievalEntity(name="Plasmodium falciparum", entity_type="pathogen"),
        ),
        queries=queries,
    )


class QueryFacetTests(unittest.TestCase):
    def test_facets_are_hashable_so_request_lineage_can_dedupe(self) -> None:
        first = QueryFacets(condition="malaria", outcome="protective efficacy")
        second = QueryFacets(condition="malaria", outcome="protective efficacy")

        self.assertEqual(len({first, second}), 1)

    def test_a_query_defaults_to_empty_facets(self) -> None:
        query = SourceQueryIntent(text="recent malaria vaccine efficacy")

        self.assertEqual(query.facets, QueryFacets())


class LiteratureQueryTests(unittest.TestCase):
    """Boolean grammar is built from stated facets, not from shredded prose."""

    def test_pubmed_query_is_built_from_facets(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="WHO prequalification thermostability requirements for malaria vaccines",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    intervention="malaria vaccine",
                    outcome="WHO prequalification thermostability requirements",
                ),
            )
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertIn("WHO prequalification thermostability requirements", query)
        self.assertIn("malaria", query)

    def test_institution_names_are_never_dropped_as_filler(self) -> None:
        """The prompt asks for authoritative institutions; nothing may delete them."""
        intent = _intent(
            SourceQueryIntent(
                text="WHO prequalification for primary series",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    outcome="WHO prequalification of the primary series",
                ),
            )
        )

        for query in (
            build_pubmed_query(intent, "general", list(intent.queries)),
            build_semantic_scholar_query(intent, "general", list(intent.queries)),
        ):
            self.assertIn("WHO", query)
            self.assertIn("primary", query)

    def test_each_query_keeps_its_own_clause_instead_of_one_term_bag(self) -> None:
        """Boolean grammar expresses several questions without interleaving them."""
        intent = _intent(
            SourceQueryIntent(
                text="thermostability requirements",
                tracks=("general",),
                facets=QueryFacets(condition="malaria", outcome="open-vial stability"),
            ),
            SourceQueryIntent(
                text="efficacy waning in children",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    population="children under five",
                    outcome="efficacy waning",
                ),
            ),
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        # Each query contributes one whole subject phrase, and the two questions
        # are alternatives rather than terms flattened into a shared bag.
        self.assertIn('"open-vial stability" OR "efficacy waning"', query)

    def test_semantic_scholar_keeps_facet_phrases_intact(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="efficacy waning in children",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    population="children under five",
                    outcome="efficacy waning",
                ),
            ),
        )

        query = build_semantic_scholar_query(intent, "general", list(intent.queries))

        self.assertIn("efficacy waning", query)
        self.assertIn("children under five", query)


class StructuredSourceRequestTests(unittest.TestCase):
    """A registry request varies with the query instead of collapsing to one."""

    def test_registry_requests_use_the_stated_population_and_outcome(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="malaria vaccine efficacy in infants",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    intervention="RTS,S",
                    population="infants",
                    outcome="protective efficacy",
                ),
            ),
        )

        requests = ClinicalTrialsSource().plan(intent)
        interventions = {request.option("intervention") for request in requests}

        # The intent-scope request is always planned; the stated facet adds one.
        self.assertEqual(interventions, {"vaccine", "RTS,S"})
        self.assertTrue(
            all(request.option("condition") == "malaria" for request in requests)
        )

    def test_distinct_facets_produce_distinct_registry_requests(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="dose volume of pediatric malaria vaccines",
                facets=QueryFacets(
                    condition="malaria",
                    intervention="malaria vaccine",
                    population="pediatric",
                ),
            ),
            SourceQueryIntent(
                text="adult malaria vaccine dose volume",
                facets=QueryFacets(
                    condition="malaria",
                    intervention="RTS,S",
                    population="adult",
                ),
            ),
        )

        requests = ClinicalTrialsSource().plan(intent)

        self.assertEqual(
            {request.option("intervention") for request in requests},
            {"vaccine", "malaria vaccine", "RTS,S"},
        )

    def test_identical_native_requests_collapse_and_keep_both_intents(self) -> None:
        shared = QueryFacets(condition="malaria", intervention="malaria vaccine")
        intent = _intent(
            SourceQueryIntent(text="first phrasing", facets=shared),
            SourceQueryIntent(text="second phrasing", facets=shared),
        )

        requests = ClinicalTrialsSource().plan(intent)
        narrowed = [r for r in requests if r.option("intervention") == "malaria vaccine"]

        self.assertEqual(len(narrowed), 1)
        self.assertEqual(len(narrowed[0].intent_ids), 2)
        self.assertEqual(len(narrowed[0].input_queries), 2)

    def test_blank_facets_fall_back_to_the_intent_scope(self) -> None:
        intent = _intent(SourceQueryIntent(text="general malaria vaccine coverage"))

        requests = ClinicalTrialsSource().plan(intent)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].option("condition"), "malaria")
        self.assertEqual(requests[0].option("intervention"), "vaccine")


if __name__ == "__main__":
    unittest.main()
