"""The indication tag is a key and a search term at once.

It is stamped on every block and result, and it is also substituted into retrieval
prompts and joined into query text. Those two jobs pull in opposite directions the
moment a name has more than one word, and the vocabulary lost that argument twice:
Group B Streptococcus became `gbs`, which in a vaccine context also means
Guillain-Barre Syndrome, and tuberculosis became `tb`, which means very little.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from shared.vocabulary import indications_for, intervention_classes, search_term

VOCAB = Path(__file__).resolve().parents[1] / "shared" / "indications.yaml"


class TagShapeTests(unittest.TestCase):
    def tags(self) -> set[str]:
        return {
            tag
            for intervention in intervention_classes()
            for tag in indications_for(intervention)
        }

    def test_every_tag_is_lowercase_words_joined_by_underscores(self) -> None:
        for tag in self.tags():
            self.assertRegex(tag, r"^[a-z0-9]+(_[a-z0-9]+)*$", tag)

    def test_every_tag_reads_as_a_search_term(self) -> None:
        """No underscore survives into query text, which is what forced acronyms."""
        for tag in self.tags():
            term = search_term(tag)
            self.assertNotIn("_", term, tag)
            self.assertEqual(term, term.strip(), tag)
            self.assertTrue(term, tag)

    def test_no_tag_is_a_bare_two_letter_abbreviation(self) -> None:
        """`tb` is terabyte, tibia, total bases. A tag has to survive a web search."""
        for tag in self.tags():
            self.assertGreater(len(tag), 2, f"{tag} is too short to be specific")

    def test_the_two_abbreviations_that_were_ambiguous_are_gone(self) -> None:
        tags = self.tags()
        self.assertNotIn("tb", tags)
        self.assertNotIn("gbs", tags)
        self.assertIn("tuberculosis", tags)
        self.assertIn("group_b_streptococcus", tags)

    def test_the_file_records_why_underscores_are_allowed(self) -> None:
        """The rule changed, so the reason has to be findable where the rule is."""
        source = VOCAB.read_text(encoding="utf-8")
        self.assertIn("search_term", source)
        self.assertIn("Guillain-Barre", source)


class SearchTermTests(unittest.TestCase):
    def test_a_single_word_tag_is_unchanged(self) -> None:
        self.assertEqual(search_term("malaria"), "malaria")

    def test_underscores_become_spaces(self) -> None:
        self.assertEqual(
            search_term("group_b_streptococcus"), "group b streptococcus"
        )


if __name__ == "__main__":
    unittest.main()
