"""Scout states each query's parts where it authors the query.

The stage that writes a query already knows the condition, intervention,
population, and outcome behind it. Stating them on the same schema-bound response
is what lets a field-addressed source use them without any downstream layer
re-reading the prose.
"""

from __future__ import annotations

import unittest

from services.searcher import QueryFacets
from services.scout.ai_contracts import query_batch
from services.scout.models import Attribute, QueryIntent
from services.scout.stages.intent_builder import build_retrieval_intents
from services.scout.stages.query_extractor import _parse_queries


class QueryContractTests(unittest.TestCase):
    def test_the_query_schema_asks_for_the_stated_facets(self) -> None:
        contract = query_batch(["doc/b-0001"], ["qt-1"])
        query = contract.schema["properties"]["queries"]["items"]["properties"]

        self.assertEqual(
            sorted(query["facets"]["properties"]),
            ["condition", "intervention", "outcome", "population"],
        )


class QueryParsingTests(unittest.TestCase):
    def test_stated_facets_are_carried_onto_the_intent(self) -> None:
        parsed = _parse_queries(
            [{
                "query": "protective efficacy of malaria vaccines in infants",
                "doc_block_ids": ["doc/b-0001"],
                "target_ids": [],
                "facets": {
                    "condition": "malaria",
                    "intervention": "malaria vaccine",
                    "population": "infants",
                    "outcome": "protective efficacy",
                },
            }],
            {"doc/b-0001"},
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].facets.condition, "malaria")
        self.assertEqual(parsed[0].facets.population, "infants")

    def test_a_response_without_facets_still_yields_a_usable_query(self) -> None:
        parsed = _parse_queries(
            [{"query": "malaria vaccine efficacy", "doc_block_ids": []}],
            set(),
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].facets, QueryFacets())


class IntentHandoffTests(unittest.TestCase):
    def test_facets_survive_the_handoff_into_searcher(self) -> None:
        attribute = Attribute("efficacy", "Vaccine efficacy.")
        intents = build_retrieval_intents(
            {
                attribute.name: [
                    QueryIntent(
                        "protective efficacy in infants",
                        ["general"],
                        ["doc/b-0001"],
                        facets=QueryFacets(
                            condition="malaria",
                            population="infants",
                            outcome="protective efficacy",
                        ),
                    )
                ]
            },
            [attribute],
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].queries[0].facets.population, "infants")


if __name__ == "__main__":
    unittest.main()
