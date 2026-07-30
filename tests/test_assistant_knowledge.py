"""Bounded product-documentation surface exposed to the Ask agent."""

from __future__ import annotations

import unittest

from services.assistant import knowledge
from services.assistant.agent import TOOLS, _system_prompt


class AssistantKnowledgeTests(unittest.TestCase):
    def test_product_knowledge_has_stable_sections_and_search(self) -> None:
        overview = knowledge.overview()
        matches = knowledge.find("stateless")

        self.assertIn("architecture", overview)
        self.assertIn("assistant", overview)
        self.assertIn("[architecture] Architecture", knowledge.read(["architecture"]))
        self.assertIn("Services", knowledge.read(["architecture"]))
        architecture_docs = knowledge.read(["workflows"])
        self.assertIn(
            "Inspector: Turns one parsed development document", architecture_docs
        )
        self.assertIn("Source-neutral intents", architecture_docs)
        self.assertIn("Bounded navigation loop", architecture_docs)
        self.assertIn("architecture", matches)
        scout_docs = knowledge.read(["scout"])
        self.assertIn("Linked product fields", scout_docs)
        self.assertIn("not synchronized database fields", scout_docs)
        self.assertIn("Included comparator cohort", scout_docs)

    def test_assistant_exposes_bounded_product_documentation_tools(self) -> None:
        tool_names = {tool["function"]["name"] for tool in TOOLS}
        prompt = _system_prompt({}, "workspace")

        self.assertIn("find_product_docs", tool_names)
        self.assertIn("read_product_docs", tool_names)
        self.assertIn("PRODUCT DOCUMENTATION MAP", prompt)
        self.assertIn("Never present product documentation as evidence", prompt)

    def test_unknown_product_knowledge_section_is_explicit(self) -> None:
        self.assertIn("unknown documentation section", knowledge.read(["missing"]))


if __name__ == "__main__":
    unittest.main()
