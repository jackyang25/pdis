"""The prompt is a stable prefix and a bounded map; no image enters it unasked."""

import json
import unittest

from shared.chat import ChatDelta, ChatTurn, ToolCall, Usage
from services.assistant import answer_stream
from services.assistant.legends import legends_for
from services.assistant.prompt import STATIC_PREFIX, system_prompt
from services.assistant.workspace import build_index
from tests.test_assistant_workspace import block, mixed_workspace, png


class RecordingClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def chat_stream(self, messages, *, tools=None, max_tokens=4000):
        self.calls.append([dict(m) for m in messages])
        turn = self.turns.pop(0)
        if turn.text:
            yield ChatDelta(text=turn.text)
        yield ChatDelta(turn=turn)


def final(text="Answer."):
    return ChatTurn(text=text, tool_calls=(), continuation=(), usage=Usage(100, 80, 10))


class PromptTests(unittest.TestCase):
    def test_prompt_starts_with_the_same_prefix_for_every_workspace(self):
        self.assertTrue(system_prompt(build_index(None, None)).startswith(STATIC_PREFIX))
        self.assertTrue(system_prompt(mixed_workspace()).startswith(STATIC_PREFIX))

    def test_legends_match_the_held_results(self):
        text = system_prompt(mixed_workspace())
        self.assertIn("This is a SCREENER result", text)
        self.assertIn("This is an INSPECTOR result", text)
        self.assertNotIn("This is an ALIGNER result", text)
        self.assertIn("ACTIVE REVIEW DRAFT", text)

    def test_a_review_draft_brings_the_scout_legend_once(self):
        draft_only = legends_for(frozenset(), has_review=True)
        self.assertIn("This is a SCOUT result", draft_only)
        self.assertIn("ACTIVE REVIEW DRAFT", draft_only)
        self.assertLess(draft_only.index("This is a SCOUT result"), draft_only.index("ACTIVE REVIEW DRAFT"))
        both = legends_for(frozenset({"scout"}), has_review=True)
        self.assertEqual(both.count("This is a SCOUT result"), 1)

    def test_the_prefix_points_at_sections_that_exist(self):
        self.assertIn("use the WORKSPACE MAP below", STATIC_PREFIX)
        self.assertIn("the ANSWERING rules above", STATIC_PREFIX)
        self.assertLess(STATIC_PREFIX.index("ANSWERING:"), STATIC_PREFIX.index("WHAT YOU CAN REACH:"))
        self.assertNotIn("OVERVIEW", STATIC_PREFIX)
        self.assertNotIn("SOURCE DOCUMENT", STATIC_PREFIX)
        self.assertIn("whenever the answer depends on a document", STATIC_PREFIX)

    def test_corrected_legends(self):
        text = system_prompt(mixed_workspace())
        self.assertIn("DOCX, PPTX or text-based PDF", text)
        self.assertNotIn("judges the iTPP, cTPP, and IPDP against each other", text)

    def test_map_does_not_grow_with_document_length(self):
        def prompt_for(slides):
            deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, slides + 1)]
            return system_prompt(build_index({"results": []}, deck))
        long, short = prompt_for(200), prompt_for(2)
        self.assertIn("200 visual(s): slides 1–200", long)
        self.assertLess(len(long) - len(short), 200)

    def test_one_ambiguity_rule_covers_runs_documents_and_versions(self):
        rule = STATIC_PREFIX[STATIC_PREFIX.index("WHEN A QUESTION COULD MEAN MORE THAN ONE THING:"):
                             STATIC_PREFIX.index("WHAT YOU CAN REACH:")]
        self.assertIn("several runs of", rule)
        self.assertIn("says \"the document\" where several are held", rule)
        self.assertIn("in more than one version", rule)
        self.assertIn("If it has one reading, answer it.", rule)
        self.assertIn("ask one short question that lists the choices", rule)
        self.assertIn("Never pick one reading silently", rule)
        self.assertLess(STATIC_PREFIX.index("ANSWERING:"), STATIC_PREFIX.index("WHEN A QUESTION COULD MEAN"))

    def test_the_prefix_sets_the_tone(self):
        self.assertIn("Write plainly and directly", STATIC_PREFIX)
        self.assertIn("No preamble, filler or sign-off.", STATIC_PREFIX)

    def test_answers_stay_on_the_question(self):
        self.assertIn("Answer what was asked.", STATIC_PREFIX)
        # Comparing claims with evidence is for questions that involve both, not every answer.
        self.assertIn("When a question involves both, line the document's claims up", STATIC_PREFIX)
        self.assertNotIn("Cross-comparison is the point", STATIC_PREFIX)

    def test_each_rule_is_stated_once(self):
        for phrase in ("whenever the answer depends on a document", "Point at a passage",
                       "say how many and link the first", "Read one"):
            self.assertLessEqual(STATIC_PREFIX.count(phrase), 1, phrase)

    def test_no_image_is_sent_up_front(self):
        client = RecordingClient([final()])
        deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 4)]
        list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Hi"}], document=deck))
        for message in client.calls[0]:
            self.assertNotIsInstance(message.get("content"), list)

    def test_viewed_images_join_the_working_list_once(self):
        call = ToolCall("c1", "view_document_visuals", json.dumps({"block_ids": ["deck/b-0002"]}))
        client = RecordingClient([ChatTurn("", (call,), ()), final()])
        deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 4)]
        chunks = list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Slide 2?"}], document=deck))
        tool_messages = [m for m in client.calls[1] if m["role"] == "tool"]
        self.assertEqual([i.block_id for i in tool_messages[0]["images"]], ["deck/b-0002"])
        self.assertEqual([c.kind for c in chunks], ["activity", "text"])

    def test_one_log_line_per_question(self):
        client = RecordingClient([final()])
        with self.assertLogs("services.assistant.agent", level="INFO") as logs:
            list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Hi"}]))
        self.assertEqual(len(logs.output), 1)
        record = json.loads(logs.output[0].split("assistant_question ", 1)[1])
        self.assertEqual(record["model_calls"], 1)
        self.assertEqual(record["input_tokens"], 100)
        self.assertEqual(record["cached_input_tokens"], 80)
        self.assertEqual(record["visuals_viewed"], 0)
