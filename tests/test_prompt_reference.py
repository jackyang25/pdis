"""The committed prompt reference must match what the generator produces.

Editing a prompt without regenerating is the only way this file can drift, so
the check exists to make that fail loudly rather than silently publishing stale
instructions.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_prompt_reference import REFERENCE, build_reference


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
            label
            for prompt in reference["prompts"]
            for label in prompt["produces"]["ui_labels"]
        }
        self.assertEqual(
            {"relationships", "grounding", "alignment", "precedent"} - published,
            set(),
            "an interface signal has no prompt behind it in the reference",
        )

    def test_reference_carries_no_empty_text(self) -> None:
        reference = json.loads(REFERENCE.read_text())
        for prompt in reference["prompts"]:
            self.assertTrue(prompt["text"].strip(), f"{prompt['id']} rendered empty")
        for framing in reference["framings"]:
            self.assertTrue(framing["text"].strip(), f"{framing['key']} rendered empty")


if __name__ == "__main__":
    unittest.main()
