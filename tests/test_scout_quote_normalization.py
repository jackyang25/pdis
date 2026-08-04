"""The excerpt check compares text, not typesetting — and only typesetting.

An excerpt earns its place in retrieval and statistics by appearing in the
source. Folding too little rejects a correct quote because a word processor
wrote a curly apostrophe; folding too much would admit an excerpt the document
never contained. Both directions are pinned here.
"""

from __future__ import annotations

import unittest

from services.scout.stages.conformity import MAX_TARGET_QUOTE_CHARS, _quote_in_text


class TypographyIsNotAMismatchTests(unittest.TestCase):
    """A model retyping a mark in ASCII has still quoted the source."""

    SOURCE = (
        "Efficacy ≥ 80% against severe disease in children 6–23 months; "
        "the sponsor’s stated target is non‑inferiority…"
    )

    def test_a_verbatim_excerpt_matches(self) -> None:
        self.assertTrue(_quote_in_text("Efficacy ≥ 80%", self.SOURCE))

    def test_ascii_retyping_of_marks_matches(self) -> None:
        for label, quote in {
            "en dash as hyphen": "children 6-23 months",
            "curly apostrophe as straight": "the sponsor's stated target",
            "greater-or-equal spelled out": "Efficacy >= 80%",
            "non-breaking hyphen as hyphen": "non-inferiority",
            "ellipsis spelled out": "non-inferiority...",
        }.items():
            with self.subTest(case=label):
                self.assertTrue(_quote_in_text(quote, self.SOURCE))

    def test_invisible_characters_are_not_a_difference(self) -> None:
        source = "co­administration with routine EPI​ vaccines"
        self.assertTrue(_quote_in_text("coadministration with routine EPI vaccines", source))

    def test_whitespace_and_case_still_do_not_matter(self) -> None:
        self.assertTrue(
            _quote_in_text("EFFICACY   ≥    80%", self.SOURCE),
            "the existing whitespace and case folding must survive",
        )


class MeaningIsStillAMismatchTests(unittest.TestCase):
    """The boundary: folding may never make a different claim verifiable.

    Each pair below is why `NFKC` is not used. It would rewrite the left side
    into the right side, letting an excerpt cite a number the document does not
    state.
    """

    def test_superscripts_are_not_digits(self) -> None:
        self.assertFalse(_quote_in_text("102 CFU/mL", "titre of 10² CFU/mL"))

    def test_fractions_are_not_spelled_out(self) -> None:
        self.assertFalse(_quote_in_text("1/2 dose", "½ dose at week 4"))

    def test_unit_ligatures_are_not_expanded(self) -> None:
        self.assertFalse(_quote_in_text("50 mg", "50 ㎒ per vial"))

    def test_opposite_comparison_operators_do_not_match(self) -> None:
        self.assertFalse(_quote_in_text("<= 80%", "Efficacy ≥ 80%"))

    def test_a_different_number_does_not_match(self) -> None:
        self.assertFalse(_quote_in_text("Efficacy >= 8%", "Efficacy ≥ 80%"))

    def test_collapsing_whitespace_does_not_join_separate_numbers(self) -> None:
        self.assertFalse(
            _quote_in_text("102", "see figure 10 2 for the curve"),
            "whitespace is collapsed, never removed, or adjacent numbers would merge",
        )


class QuoteLengthTests(unittest.TestCase):
    def test_the_cap_is_a_short_excerpt_not_a_whole_passage(self) -> None:
        # Rejections are reported with one code, so the cap is stated here to
        # keep it visible next to the comparison it shares that code with.
        self.assertEqual(MAX_TARGET_QUOTE_CHARS, 800)


if __name__ == "__main__":
    unittest.main()
