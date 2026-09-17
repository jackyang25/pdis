"""Review help uses the existing read-only tools without making drafts final."""

import copy
import json
import unittest

from services.assistant.agent import _system_prompt, answer_stream
from services.assistant.registry import held_result_types
from shared.chat import ChatDelta, ChatTurn, ToolCall


class AssistantReviewContextTests(unittest.TestCase):
    def test_active_review_gets_draft_instructions_but_cannot_satisfy_final_result_skills(self):
        for phase in ("target_review", "evidence_review"):
            bundle = {"results": [], "active_review": {
                "result_type": "scout", "phase": phase,
                "selected_item": {"kind": "target", "target_id": "t1"},
                "analysis": {"phase": phase},
            }}
            prompt = _system_prompt(bundle, "workspace")
            self.assertIn("ACTIVE REVIEW DRAFT", prompt)
            self.assertIn("not a final result", prompt)
            self.assertIn("selected_item", prompt)
            self.assertEqual(held_result_types(bundle), frozenset())
        self.assertNotIn("ACTIVE REVIEW DRAFT", _system_prompt({"results": []}, "workspace"))

    def test_registered_readers_return_review_and_document_context_without_mutating_it(self):
        bundle = {"results": [], "active_review": {
            "result_type": "scout", "phase": "target_review",
            "selected_item": {"kind": "target", "target_id": "t1"},
            "analysis": {"quantitative_ledger": {"targets": [{"id": "t1", "review_status": "needs_review"}]}},
        }}
        before = copy.deepcopy(bundle)
        requests = []

        class Client:
            def chat_stream(self, messages, **kwargs):
                requests.append(copy.deepcopy(messages))
                if len(requests) == 1:
                    yield ChatDelta(turn=ChatTurn("", (
                        ToolCall("review", "read_result", '{"path":"active_review.analysis.quantitative_ledger.targets[0]"}'),
                        ToolCall("source", "read_document", '{"block_ids":["doc/b1"]}'),
                    ), None))
                else:
                    yield ChatDelta(text="This is a proposed target awaiting your decision.")
                    yield ChatDelta(turn=ChatTurn("", (), None))

        list(answer_stream(Client(), bundle, "workspace", [{"role": "user", "content": "Explain this target"}],
                           document=[{"id": "doc/b1", "doc_id": "doc", "content": "Target efficacy is 80%."}]))
        responses = [message for message in requests[1] if message["role"] == "tool"]
        self.assertEqual(json.loads(responses[0]["content"])["review_status"], "needs_review")
        self.assertIn("Target efficacy is 80%", responses[1]["content"])
        self.assertEqual(bundle, before)
