"""The digest describes the list; the nominations are what the list leaves out.

Both come from one call, and the tests that matter are the ones that keep them from
becoming a second priority list: a nomination repeating a listed item, a nomination
nobody can open, or more of them than a reader is meant to read.
"""

from __future__ import annotations

import unittest

from services.assistant import (
    MAX_NOMINATIONS,
    PriorityItemInput,
    PriorityRequest,
    read_priorities,
)
from services.assistant.priorities import (
    build_system_prompt,
    build_user_message,
    digest_schema,
)


class FakeClient:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        self.calls.append({
            "system": system_prompt,
            "user": user_message,
            "schema": schema,
        })
        return None if self.payload is None else dict(self.payload)


def request(**overrides) -> PriorityRequest:
    defaults = dict(
        authority="Reads one document against its authored rubric.",
        order_note="by level, then rubric order",
        items=(
            PriorityItemInput(
                id="f-1",
                label="Primary user groups",
                qualifier="Medical Need",
                statement="The document does not identify them.",
            ),
        ),
        analysis={"sections": [{"name": "Medical Need"}]},
        block_ids=frozenset({"doc/b-0001", "doc/b-0002"}),
        org="bmgf",
        intervention_class="monoclonal_antibody",
        indication="tuberculosis",
    )
    defaults.update(overrides)
    return PriorityRequest(**defaults)


def payload(nominations: list[dict] | None = None) -> dict:
    return {
        "digest": "  Most of what is open sits in one section.  ",
        "nominations": nominations if nominations is not None else [],
    }


class DigestTests(unittest.TestCase):
    def read(self, body: dict | None, **overrides):
        client = FakeClient(body)
        return read_priorities(request(**overrides), llm_client=client), client

    def test_the_digest_is_returned_as_one_line_of_prose(self) -> None:
        result, _ = self.read(payload())
        self.assertEqual(result.digest, "Most of what is open sits in one section.")
        self.assertEqual(result.nominations, [])

    def test_an_empty_digest_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.read({"digest": "   ", "nominations": []})

    def test_no_structured_answer_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.read(None)

    def test_a_nomination_is_kept_with_its_citation(self) -> None:
        result, _ = self.read(payload([{
            "label": "Duration of protection",
            "statement": "Stated but unquantified, and three later units depend on it.",
            "cited_block_ids": ["doc/b-0002", "doc/b-0002"],
        }]))
        self.assertEqual(len(result.nominations), 1)
        self.assertEqual(result.nominations[0].cited_block_ids, ["doc/b-0002"])

    def test_a_nomination_repeating_a_listed_item_is_dropped(self) -> None:
        """Otherwise one finding appears in two layers, which is the whole failure mode."""
        result, _ = self.read(payload([{
            "label": "  primary   USER groups ",
            "statement": "Also worth a look.",
            "cited_block_ids": ["doc/b-0001"],
        }]))
        self.assertEqual(result.nominations, [])

    def test_a_nomination_nobody_can_open_is_dropped(self) -> None:
        """The panel's claim is that everything in it can be opened."""
        for cited in ([], ["doc/b-9999"]):
            result, _ = self.read(payload([{
                "label": "Something",
                "statement": "Worth a look.",
                "cited_block_ids": cited,
            }]))
            self.assertEqual(result.nominations, [], cited)

    def test_nominations_are_capped(self) -> None:
        """A second look, not a second list."""
        result, _ = self.read(payload([
            {
                "label": f"Item {index}",
                "statement": "Worth a look.",
                "cited_block_ids": ["doc/b-0001"],
            }
            for index in range(MAX_NOMINATIONS + 3)
        ]))
        self.assertEqual(len(result.nominations), MAX_NOMINATIONS)

    def test_a_citation_is_offered_only_from_blocks_that_exist(self) -> None:
        _, client = self.read(payload())
        schema = client.calls[0]["schema"]
        enum = schema["properties"]["nominations"]["items"]["properties"][
            "cited_block_ids"
        ]["items"]["enum"]
        self.assertEqual(enum, ["doc/b-0001", "doc/b-0002"])

    def test_a_result_with_no_blocks_still_produces_a_digest(self) -> None:
        """Scout's utility outputs retain none, and the schema cannot hold an empty enum."""
        result, client = self.read(payload(), block_ids=frozenset())
        self.assertTrue(result.digest)
        cited = client.calls[0]["schema"]["properties"]["nominations"]["items"][
            "properties"
        ]["cited_block_ids"]["items"]
        self.assertNotIn("enum", cited)

    def test_a_nomination_survives_when_the_result_retains_no_blocks(self) -> None:
        # With nothing to check a citation against, dropping every nomination would make
        # the layer silently unavailable rather than unsourced.
        result, _ = self.read(
            payload([{
                "label": "Something",
                "statement": "Worth a look.",
                "cited_block_ids": [],
            }]),
            block_ids=frozenset(),
        )
        self.assertEqual(len(result.nominations), 1)


class BoundsTests(unittest.TestCase):
    """The two inputs that were unbounded, and the failure that hid it.

    Both are the same shape of bug: a limit nothing stated, hit only by the largest
    results — the ones with the most to say — and reported as a skeleton followed by
    nothing.
    """

    def test_a_result_with_many_blocks_still_produces_a_schema(self) -> None:
        """Structured outputs cap an enum past 250 values at 7,500 characters of total
        string length. A block ID runs about fifteen characters, so a few hundred blocks
        made the schema itself invalid and the provider rejected the whole request."""
        from services.assistant.priorities import MAX_ENUMERATED_BLOCK_IDS

        many = [f"doc/b-{index:04d}" for index in range(MAX_ENUMERATED_BLOCK_IDS + 400)]
        cited = digest_schema(many)["properties"]["nominations"]["items"]["properties"][
            "cited_block_ids"
        ]["items"]
        self.assertNotIn("enum", cited)
        self.assertEqual(cited["type"], "string")

    def test_a_small_result_still_gets_the_closed_enum(self) -> None:
        """Where it fits, it stays: the model cannot then name a block that does not
        exist, which is a better guarantee than checking afterwards."""
        cited = digest_schema(["doc/b-0001", "doc/b-0002"])["properties"]["nominations"][
            "items"
        ]["properties"]["cited_block_ids"]["items"]
        self.assertEqual(cited["enum"], ["doc/b-0001", "doc/b-0002"])

    def test_an_unenumerated_citation_is_still_checked(self) -> None:
        """The enum was belt to existing braces, not the guarantee itself."""
        blocks = frozenset(f"doc/b-{index:04d}" for index in range(600))
        result, _ = DigestTests.read(
            DigestTests(),
            payload([
                {
                    "label": "Invented",
                    "statement": "Worth a look.",
                    "cited_block_ids": ["doc/b-9999"],
                }
            ]),
            block_ids=blocks,
        )
        self.assertEqual(result.nominations, [])

    def test_an_oversized_analysis_stands_the_nominations_down(self) -> None:
        """Rather than truncating it. A model handed half an analysis with no note would
        nominate from the half it saw and present it as a reading of the whole."""
        from services.assistant.priorities import MAX_ANALYSIS_CHARACTERS

        message = build_user_message(
            request(analysis="x" * (MAX_ANALYSIS_CHARACTERS + 1))
        )
        self.assertIn("too large to include", message)
        self.assertIn("empty `nominations`", message)
        # The list is still there, because the digest describes the list and nothing else.
        self.assertIn("Priorities already selected", message)

    def test_an_analysis_within_the_bound_is_sent_whole(self) -> None:
        message = build_user_message(request(analysis={"sections": ["one"]}))
        self.assertIn("The full analysis", message)
        self.assertNotIn("too large", message)


class PromptTests(unittest.TestCase):
    def test_the_prompt_names_no_tool_and_no_domain(self) -> None:
        """One prompt serves every tool; a fifth is served by it unchanged."""
        prompt = build_system_prompt().lower()
        for word in (
            "inspector", "aligner", "scout", "expert",
            "itpp", "ctpp", "ipdp", "vaccine", "tuberculosis",
        ):
            self.assertNotIn(word, prompt, word)

    def test_the_prompt_forbids_reordering_and_scoring(self) -> None:
        prompt = build_system_prompt().lower()
        self.assertIn("do not re-rank", prompt)
        self.assertIn("do not score", prompt)

    def test_the_message_puts_the_list_before_the_analysis(self) -> None:
        """First question is what is already covered; the analysis answers a later one."""
        message = build_user_message(request())
        self.assertLess(
            message.index("Priorities already selected"), message.index("The full analysis")
        )

    def test_the_message_carries_the_authority_and_the_domain_in_words(self) -> None:
        message = build_user_message(request())
        self.assertIn("against its authored rubric", message)
        # De-underscored, like every other place a context tag becomes text.
        self.assertIn("monoclonal antibody", message)
        self.assertNotIn("monoclonal_antibody", message)

    def test_the_schema_is_closed(self) -> None:
        schema = digest_schema(["doc/b-0001"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(sorted(schema["required"]), ["digest", "nominations"])


if __name__ == "__main__":
    unittest.main()
