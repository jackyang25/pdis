"""An offer is a search the reader can run, proposed by the agent and never run by it."""

from __future__ import annotations

import inspect
import json
import unittest

from api.operations.searcher import SearchInput
from api.routes.assistant import sse
from services.assistant import Chunk, answer_stream
from services.assistant.offers import OFFER_RULES, offer_parameters, search_offer, SearchOffer
from services.assistant.prompt import STATIC_PREFIX
from services.assistant.registry import VERBS
from services.searcher import (
    ENTITY_TYPES,
    SEARCH_ENTITIES_DESCRIPTION,
    SEARCH_ENTITY_FIELDS,
    SEARCH_TEXT_FIELDS,
    run_pipeline,
    source_specs,
)
from shared.chat import ChatTurn, ToolCall
from tests.test_assistant_prompt import RecordingClient, final


class SearchFieldContractTests(unittest.TestCase):
    """Searcher owns what a search accepts; every caller names the same fields."""

    def test_every_text_field_is_a_run_pipeline_parameter(self):
        self.assertLessEqual(set(SEARCH_TEXT_FIELDS), set(inspect.signature(run_pipeline).parameters))

    def test_the_api_request_is_the_text_fields_plus_the_structured_inputs(self):
        self.assertEqual(
            set(SearchInput.model_fields),
            set(SEARCH_TEXT_FIELDS) | {"sources", "entities", "max_findings"},
        )

    def test_every_field_says_what_it_means(self):
        for name, meaning in {**SEARCH_TEXT_FIELDS, **SEARCH_ENTITY_FIELDS}.items():
            self.assertTrue(meaning.strip(), name)

    def test_the_api_request_describes_fields_in_searchers_words(self):
        # MCP publishes these descriptions; the Assistant's offer reads the same ones.
        for name, meaning in SEARCH_TEXT_FIELDS.items():
            self.assertEqual(SearchInput.model_fields[name].description, meaning, name)
        self.assertEqual(SearchInput.model_fields["entities"].description, SEARCH_ENTITIES_DESCRIPTION)
        entity = SearchInput.model_fields["entities"].annotation.__args__[0]
        for name, meaning in SEARCH_ENTITY_FIELDS.items():
            self.assertEqual(entity.model_fields[name].description, meaning, name)

    def test_the_offer_schema_is_built_from_searcher(self):
        schema = offer_parameters()
        properties = schema["properties"]
        self.assertEqual(set(properties), set(SEARCH_TEXT_FIELDS) | {"sources", "entities"})
        for name, meaning in SEARCH_TEXT_FIELDS.items():
            self.assertTrue(properties[name]["description"].startswith(meaning), name)
        self.assertTrue(properties["entities"]["description"].startswith(SEARCH_ENTITIES_DESCRIPTION))
        self.assertLessEqual(set(OFFER_RULES), set(properties))
        self.assertEqual(
            set(schema["properties"]["sources"]["items"]["enum"]),
            {spec.key for spec in source_specs()},
        )
        self.assertEqual(
            set(schema["properties"]["entities"]["items"]["properties"]["entity_type"]["enum"]),
            set(ENTITY_TYPES),
        )


class SearchOfferTests(unittest.TestCase):
    def test_untrusted_arguments_become_a_bounded_offer(self):
        offer = search_offer({
            "query": "  maternal RSV vaccine efficacy  ", "condition": "RSV", "region": 7,
            "published_since": "last year", "product": "",
            "sources": ["who_guidelines", "made_up", "who_guidelines"],
            "entities": [{"name": "RSVpreF", "entity_type": "vaccine"}, {"name": "x", "entity_type": "nonsense"}],
        })
        self.assertIsInstance(offer, SearchOffer)
        self.assertEqual(offer.to_event(), {
            "tool": "searcher",
            "fields": {"query": "maternal RSV vaccine efficacy", "condition": "RSV"},
            "sources": [{"key": "who_guidelines", "label": "WHO Guidelines"}],
            "entities": [{"name": "RSVpreF", "entity_type": "vaccine"}],
        })
        self.assertIsInstance(search_offer({"condition": "RSV"}), str)

    def test_an_offer_with_no_sources_leaves_searchers_defaults(self):
        self.assertNotIn("sources", search_offer({"query": "RSV"}).to_event())

    def test_the_loop_sends_the_offer_on_its_own_event_and_tells_the_model_nothing_ran(self):
        client = RecordingClient([
            ChatTurn("", (ToolCall("c1", "offer_search", json.dumps({"query": "RSV efficacy", "condition": "RSV"})),), ()),
            final("Your results do not cover this."),
        ])
        chunks = list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Any trials?"}]))
        offers = [chunk for chunk in chunks if chunk.kind == "offer"]
        self.assertEqual(offers, [Chunk("offer", data={"tool": "searcher", "fields": {"query": "RSV efficacy", "condition": "RSV"}})])
        self.assertNotIn("RSV efficacy", "".join(chunk.text for chunk in chunks if chunk.kind == "text"))
        self.assertIn("You have not searched", client.calls[1][-1]["content"])

    def test_an_offer_is_framed_as_its_json_object(self):
        events = list(sse(iter([Chunk("offer", data={"tool": "searcher", "fields": {"query": "q"}})])))
        self.assertEqual(events[0], 'event: offer\ndata: {"tool": "searcher", "fields": {"query": "q"}}\n\n')

    def test_the_prompt_says_an_offer_is_never_run_by_the_agent(self):
        self.assertIn("offer_search", STATIC_PREFIX)
        self.assertIn("proposed to the reader to run, never run by you", STATIC_PREFIX)
        self.assertIn("Runs nothing", VERBS["offer_search"].description)


if __name__ == "__main__":
    unittest.main()
