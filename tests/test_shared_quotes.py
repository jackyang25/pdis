"""One rule for whether a quotation is its source's own words."""

import unittest

from shared.quotes import in_one_fragment, quote_in_text

SOURCE = (
    "Subunit vaccines with the prefusion F protein have demonstrated significant protection in older "
    "adults. Several trials followed. Efficacy against severe disease was 82.4% through 90 days."
)


class QuoteTests(unittest.TestCase):
    def test_a_contiguous_quote_is_found_whatever_its_typesetting(self) -> None:
        self.assertTrue(quote_in_text("Efficacy against severe disease was 82.4%", SOURCE))
        self.assertTrue(quote_in_text("prefusion F protein have demonstrated", SOURCE.replace(" ", "  ")))

    def test_an_elided_quote_is_accepted_only_when_asked_and_only_in_order(self) -> None:
        elided = "Subunit vaccines with the prefusion F protein [...] Efficacy against severe disease was 82.4%"
        # Strict by default: a number's measurement must be one contiguous span.
        self.assertFalse(quote_in_text(elided, SOURCE))
        self.assertTrue(quote_in_text(elided, SOURCE, allow_elision=True))
        self.assertTrue(quote_in_text(elided.replace("[...]", "…"), SOURCE, allow_elision=True))
        # Every run is checked word for word, and in the source's order.
        self.assertFalse(quote_in_text("Efficacy against severe disease ... Subunit vaccines", SOURCE, allow_elision=True))
        self.assertFalse(quote_in_text("Subunit vaccines ... efficacy was 99%", SOURCE, allow_elision=True))

    def test_a_number_must_sit_inside_one_quoted_run(self) -> None:
        elided = "protection in older adults ... severe disease was 82.4% through 90 days"
        self.assertTrue(in_one_fragment("82.4%", elided))
        # Words that span the elision would set the figure beside another sentence.
        self.assertFalse(in_one_fragment("older adults severe disease was 82.4%", elided))


if __name__ == "__main__":
    unittest.main()
