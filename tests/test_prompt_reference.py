"""The committed prompt reference must match what the generator produces.

Editing a prompt without regenerating is the only way this file can drift, so
the check exists to make that fail loudly rather than silently publishing stale
instructions.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_prompt_reference import CATALOGS, REFERENCE, build_reference
from shared.prompt_catalog import catalog_reference


class PromptReferenceTest(unittest.TestCase):
    def test_committed_reference_matches_generator(self) -> None:
        self.assertTrue(REFERENCE.exists(), "prompt reference has not been generated")
        self.assertEqual(
            json.loads(REFERENCE.read_text()),
            build_reference(),
            "run PYTHONPATH=. .venv/bin/python scripts/generate_prompt_reference.py",
        )

    def test_every_signal_topic_has_at_least_one_prompt(self) -> None:
        """A published topic with no prompt would read as an evasive gap."""
        reference = json.loads(REFERENCE.read_text())
        published = {
            (prompt["tool"], label)
            for prompt in reference["prompts"]
            for label in prompt["produces"]["ui_labels"]
        }
        expected = {
            ("scout", "relationships"),
            ("scout", "grounding"),
            ("scout", "alignment"),
            ("scout", "precedent"),
            ("inspector", "completeness"),
            ("inspector", "adherence"),
            ("inspector", "rigor"),
            ("inspector", "presence"),
            ("inspector", "consistency"),
        }
        self.assertEqual(
            expected - published,
            set(),
            "an interface signal has no prompt behind it, so its tooltip cannot link",
        )

    def test_every_tool_with_a_catalog_is_published(self) -> None:
        """A tool absent from the reference has an empty documentation panel."""
        reference = json.loads(REFERENCE.read_text())
        declared = {entry.tool for catalog in CATALOGS for entry in catalog}
        published = {prompt["tool"] for prompt in reference["prompts"]}
        self.assertEqual(declared, published)
        self.assertEqual(
            declared,
            {"chunker", "inspector", "aligner", "scout"},
            "add the new tool's catalog to CATALOGS, or remove it here deliberately",
        )

    def test_documentation_anchors_are_unique(self) -> None:
        """A tooltip links by anchor, so two prompts sharing one would misroute.

        Stage names are unique only within a tool - Inspector and a future tool
        may both call a stage `grader` - which is why the anchor carries both.
        """
        reference = json.loads(REFERENCE.read_text())
        anchors = [
            catalog_reference(prompt["tool"], prompt["stage"])
            for prompt in reference["prompts"]
        ]
        duplicates = sorted({a for a in anchors if anchors.count(a) > 1})
        # Several prompts may share a stage panel (Scout's conformity sends
        # three), so duplicates are expected; what must hold is that an anchor
        # never spans two tools.
        for anchor in duplicates:
            tools = {
                prompt["tool"]
                for prompt in reference["prompts"]
                if catalog_reference(prompt["tool"], prompt["stage"]) == anchor
            }
            self.assertEqual(len(tools), 1, f"{anchor} resolves to more than one tool")

    def test_reference_carries_no_empty_text(self) -> None:
        reference = json.loads(REFERENCE.read_text())
        for prompt in reference["prompts"]:
            self.assertTrue(prompt["text"].strip(), f"{prompt['id']} rendered empty")
        for framing in reference["framings"]:
            self.assertTrue(framing["text"].strip(), f"{framing['key']} rendered empty")


if __name__ == "__main__":
    unittest.main()
