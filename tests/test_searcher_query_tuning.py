"""A request must be reachable, not merely precise.

Facets carry roles. The condition anchors every request for an intent. One
subject phrase is what a single query asks. Remaining facets qualify meaning for
downstream assessment and must never become Boolean conjuncts, because each one
added to an AND turns the request into a coincidence requirement that real
records rarely satisfy.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from services.searcher import (
    QueryFacets,
    RetrievalEntity,
    RetrievalIntent,
    SourceQueryIntent,
)
from services.searcher.sources.clinicaltrials import ClinicalTrialsSource
from services.searcher.sources.fda import FDASource
from services.searcher.sources.literature import (
    build_pubmed_query,
    build_semantic_scholar_query,
)
from services.searcher.sources.planning import facet_groups


def _intent(*queries: SourceQueryIntent) -> RetrievalIntent:
    return RetrievalIntent(
        scope_ref="vaccine.thermostability",
        topic="thermostability",
        description="Stability across temperature ranges.",
        indication="malaria",
        intervention_class="vaccine",
        entities=(
            RetrievalEntity(name="Plasmodium falciparum", entity_type="pathogen"),
        ),
        queries=queries,
    )


def _named_entity_intent(*queries: SourceQueryIntent) -> RetrievalIntent:
    """An intent whose document named several pathogens and a product class."""
    return replace(
        _intent(*queries),
        entities=(
            RetrievalEntity(name="Plasmodium falciparum", entity_type="pathogen"),
            RetrievalEntity(name="Plasmodium vivax", entity_type="pathogen"),
            RetrievalEntity(name="DNA vaccines", entity_type="vaccine"),
        ),
    )


class ReachableLiteratureQueryTests(unittest.TestCase):
    def test_qualifier_facets_never_become_required_conjuncts(self) -> None:
        """Two exact phrases both required is a coincidence, not a search."""
        intent = _intent(
            SourceQueryIntent(
                text="thermostability and freeze sensitivity of malaria vaccines",
                tracks=("general",),
                facets=QueryFacets(
                    condition="malaria",
                    intervention="vaccine thermostability",
                    outcome="freeze sensitivity",
                ),
            )
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertIn('"freeze sensitivity"', query)
        self.assertNotIn('"vaccine thermostability" AND "freeze sensitivity"', query)
        self.assertNotIn('"freeze sensitivity" AND "vaccine thermostability"', query)

    def test_several_queries_are_alternatives_rather_than_requirements(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="open vial stability",
                tracks=("general",),
                facets=QueryFacets(condition="malaria", outcome="open-vial stability"),
            ),
            SourceQueryIntent(
                text="storage temperature tolerance",
                tracks=("general",),
                facets=QueryFacets(condition="malaria", outcome="storage temperature"),
            ),
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertIn('"open-vial stability" OR "storage temperature"', query)

    def test_the_anchor_scopes_the_request_exactly_once(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="a", facets=QueryFacets(condition="malaria", outcome="efficacy")
            ),
            SourceQueryIntent(
                text="b", facets=QueryFacets(condition="malaria", outcome="durability")
            ),
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertEqual(query.count("malaria"), 1)
        self.assertTrue(query.startswith("malaria AND "))

    def test_a_query_without_facets_falls_back_to_its_prose(self) -> None:
        intent = _intent(SourceQueryIntent(text="WHO prequalification requirements"))

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertIn("WHO prequalification requirements", query)


class PhraseQuotingTests(unittest.TestCase):
    """Quote a value only when it is one phrase."""

    def test_a_value_holding_several_concepts_is_not_quoted_as_one_phrase(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="thermostability requirements",
                facets=QueryFacets(
                    condition="malaria",
                    outcome="freeze sensitivity, controlled temperature chain eligibility",
                ),
            )
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertNotIn(
            '"freeze sensitivity, controlled temperature chain eligibility"', query
        )
        self.assertIn("freeze sensitivity", query)

    def test_a_single_phrase_is_still_quoted_so_its_words_stay_together(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="efficacy in young children",
                facets=QueryFacets(condition="malaria", outcome="children under five"),
            )
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertIn('"children under five"', query)

    def test_semantic_scholar_keeps_subject_phrases_and_the_anchor(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="open vial stability",
                facets=QueryFacets(condition="malaria", outcome="open-vial stability"),
            )
        )

        query = build_semantic_scholar_query(intent, "general", list(intent.queries))

        self.assertIn("malaria", query)
        self.assertIn("open-vial stability", query)


class AdditiveRequestTests(unittest.TestCase):
    """Narrowed requests are added to the intent's own scope, never substituted."""

    def test_the_intent_scope_request_is_always_planned(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="RTS,S trials",
                facets=QueryFacets(condition="malaria", intervention="RTS,S"),
            )
        )

        requests = ClinicalTrialsSource().plan(intent)
        interventions = {request.option("intervention") for request in requests}

        self.assertIn("vaccine", interventions)
        self.assertIn("RTS,S", interventions)

    def test_the_scope_request_carries_every_query_in_its_lineage(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="RTS,S", facets=QueryFacets(condition="malaria", intervention="RTS,S")
            ),
            SourceQueryIntent(
                text="R21", facets=QueryFacets(condition="malaria", intervention="R21")
            ),
        )

        requests = ClinicalTrialsSource().plan(intent)
        scope = next(r for r in requests if r.option("intervention") == "vaccine")

        self.assertEqual(len(scope.intent_ids), 2)

    def test_a_source_request_budget_bounds_the_narrowed_requests(self) -> None:
        intent = _intent(*[
            SourceQueryIntent(
                text=f"product {index}",
                facets=QueryFacets(condition="malaria", intervention=f"product-{index}"),
            )
            for index in range(9)
        ])

        groups = facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={"condition": "malaria", "intervention": "vaccine"},
            limit=3,
        )

        self.assertEqual(len(groups), 3)
        # The scope request survives truncation; precision is what gets dropped.
        self.assertEqual(groups[0][0]["intervention"], "vaccine")

    def test_no_budget_keeps_every_distinct_scope(self) -> None:
        intent = _intent(*[
            SourceQueryIntent(
                text=f"product {index}",
                facets=QueryFacets(condition="malaria", intervention=f"product-{index}"),
            )
            for index in range(4)
        ])

        groups = facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={"condition": "malaria", "intervention": "vaccine"},
        )

        self.assertEqual(len(groups), 5)


class SingleAnchorTests(unittest.TestCase):
    """An anchor scopes a request once.

    A document names its pathogens, comparators and institutions. Requiring all
    of them at once describes no real record, so only one anchor may enter a
    Boolean expression. The rest keep their meaning in lineage and in grammars
    where an extra phrase only sharpens ranking.
    """

    def test_every_declared_entity_does_not_become_a_required_conjunct(self) -> None:
        intent = _named_entity_intent(
            SourceQueryIntent(
                text="storage temperature tolerance",
                facets=QueryFacets(condition="malaria", outcome="storage temperature"),
            )
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertEqual(query, 'malaria AND "storage temperature"')

    def test_the_anchor_falls_back_to_a_declared_entity(self) -> None:
        """A document that states no indication still scopes its requests."""
        intent = replace(
            _named_entity_intent(
                SourceQueryIntent(
                    text="storage temperature tolerance",
                    facets=QueryFacets(outcome="storage temperature"),
                )
            ),
            indication="",
        )

        query = build_pubmed_query(intent, "general", list(intent.queries))

        self.assertTrue(query.startswith('"Plasmodium falciparum" AND '))

    def test_a_plain_text_grammar_still_names_every_declared_entity(self) -> None:
        """Excluded from an AND is not excluded from the request."""
        intent = _named_entity_intent(
            SourceQueryIntent(
                text="storage temperature tolerance",
                facets=QueryFacets(condition="malaria", outcome="storage temperature"),
            )
        )

        query = build_semantic_scholar_query(intent, "general", list(intent.queries))

        for name in ("malaria", "Plasmodium falciparum", "Plasmodium vivax"):
            self.assertIn(name, query)


class FieldAddressedAnchorTests(unittest.TestCase):
    """A field-addressed source anchors on the intent, not on a restatement.

    An intent's scope is stated once and validated against the document. A query
    that restates that scope in its own words has narrowed nothing, and the
    source's index is not guaranteed to hold the restatement, so it must not
    consume one of the source's requests.
    """

    def test_an_anchor_field_ignores_a_per_query_restatement_of_scope(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="paludisme vaccin",
                facets=QueryFacets(condition="paludisme"),
            )
        )

        groups = facet_groups(
            intent,
            fields=("condition",),
            fallbacks={"condition": "malaria"},
            anchors=("condition",),
        )

        self.assertEqual([scope["condition"] for scope, _ in groups], ["malaria"])

    def test_a_narrowing_field_still_earns_its_own_request(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="RTS,S trials",
                facets=QueryFacets(condition="paludisme", intervention="RTS,S"),
            )
        )

        groups = facet_groups(
            intent,
            fields=("condition", "intervention"),
            fallbacks={"condition": "malaria", "intervention": "vaccine"},
            anchors=("condition",),
        )

        self.assertEqual(
            [(scope["condition"], scope["intervention"]) for scope, _ in groups],
            [("malaria", "vaccine"), ("malaria", "RTS,S")],
        )

    def test_a_restatement_does_not_spend_a_capped_source_request(self) -> None:
        intent = _intent(
            SourceQueryIntent(
                text="malaria vaccine labelling",
                facets=QueryFacets(condition="malaria"),
            ),
            SourceQueryIntent(
                text="paludisme vaccin etiquetage",
                facets=QueryFacets(condition="paludisme"),
            ),
        )

        requests = FDASource().plan(intent)

        self.assertEqual([request.query for request in requests], ["indication:malaria"])
        self.assertEqual(len(requests[0].intent_ids), 2)


if __name__ == "__main__":
    unittest.main()
