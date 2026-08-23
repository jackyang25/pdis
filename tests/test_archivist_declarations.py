"""What the corpus indexes, what it fences each column against, and what it skips.

These are the tests that keep a declaration from rotting into a lie. Every column and
every sibling it names is checked against the shared vocabulary, so renaming or removing
an attribute fails here instead of leaving a prompt that describes a field which no longer
exists. `MISSING_INDEXED_CLASSES` is checked the same way in both directions: an entry
naming a class that has since been indexed, or a class the vocabulary no longer declares,
is a stale gap rather than an honest one.

The quantity parser is here too, and its tests are mostly about what it refuses. It parses
about half of real values and leaves the rest alone, which is the design: `stated` always
carries the document's words, so a magnitude is a convenience for sorting and never the
authority.
"""

from __future__ import annotations

import unittest

from services.archivist import (
    INDEXED_ATTRIBUTES,
    MISSING_INDEXED_CLASSES,
    QUANTITY_KINDS,
    filterable_attributes,
    indexed_attribute,
    indexed_attributes,
    tag_vocabulary,
)
from services.archivist.quantity import parse_quantity
from shared.vocabulary import attribute_definitions, intervention_classes


class DeclarationTest(unittest.TestCase):
    def test_every_column_is_a_real_attribute_of_its_class(self) -> None:
        for intervention_class, columns in INDEXED_ATTRIBUTES.items():
            declared = {d.name for d in attribute_definitions(intervention_class)}
            for column in columns:
                with self.subTest(column=column.attribute):
                    self.assertIn(column.attribute, declared)

    def test_every_fenced_sibling_is_a_real_attribute_of_the_same_class(self) -> None:
        """The point of naming siblings rather than describing the boundary in prose.

        A renamed attribute breaks this test. Described in prose, it would leave a
        confident sentence in a prompt about a field that no longer exists, and nothing
        would notice.
        """
        for intervention_class, columns in INDEXED_ATTRIBUTES.items():
            declared = {d.name for d in attribute_definitions(intervention_class)}
            for column in columns:
                for sibling in column.not_confused_with:
                    with self.subTest(column=column.attribute, sibling=sibling):
                        self.assertIn(sibling, declared)

    def test_a_column_is_filterable_exactly_when_it_declares_tags(self) -> None:
        """One axis, not two. A separate flag could disagree with the vocabulary."""
        for columns in INDEXED_ATTRIBUTES.values():
            for column in columns:
                self.assertEqual(column.filterable, bool(column.tags))

    def test_every_declared_quantity_is_one_the_parser_knows(self) -> None:
        for columns in INDEXED_ATTRIBUTES.values():
            for column in columns:
                if column.quantity:
                    self.assertIn(column.quantity, QUANTITY_KINDS)

    def test_a_column_never_fences_itself(self) -> None:
        for columns in INDEXED_ATTRIBUTES.values():
            for column in columns:
                self.assertNotIn(column.attribute, column.not_confused_with)

    def test_vaccine_declares_the_two_columns_a_reader_filters_by(self) -> None:
        """Population and delivery channel, and deliberately not use case.

        A use case distinguishes what a vaccine does - blocking transmission against
        preventing disease - which is not how it reaches an arm. The archive is asked
        about the channel, so the channel is the filter and `use_case` is fenced out of it.
        """
        filterable = [column.attribute for column in filterable_attributes("vaccine")]
        self.assertEqual(
            filterable, ["vaccine.target_population", "vaccine.delivery_strategy"]
        )
        self.assertIn(
            "vaccine.use_case",
            indexed_attribute("vaccine", "vaccine.delivery_strategy").not_confused_with,
        )

    def test_shelf_life_and_thermostability_are_fenced_against_each_other(self) -> None:
        """The confusion this design exists for.

        Both are printed under "Stability" and both read as "at least 24 months". One is
        potency on a shelf, the other a temperature regime, and a column that absorbed
        the wrong one would be wrong in a way no downstream check could see.
        """
        shelf = indexed_attribute("vaccine", "vaccine.shelf_life")
        thermo = indexed_attribute("vaccine", "vaccine.thermostability")
        self.assertIn("vaccine.thermostability", shelf.not_confused_with)
        self.assertIn("vaccine.shelf_life", thermo.not_confused_with)

    def test_duration_of_protection_is_fenced_against_shelf_life(self) -> None:
        """Months of immunity in a person against months of potency on a shelf."""
        self.assertIn(
            "vaccine.shelf_life",
            indexed_attribute("vaccine", "vaccine.duration_of_protection").not_confused_with,
        )

    def test_a_tag_is_never_declared_twice_in_one_vocabulary(self) -> None:
        for intervention_class, columns in INDEXED_ATTRIBUTES.items():
            for column in columns:
                tags = tag_vocabulary(intervention_class, column.attribute)
                self.assertEqual(len(set(tags)), len(tags))


class DeclaredGapTest(unittest.TestCase):
    """A gap that has closed, or one that names something gone, is a stale gap."""

    def test_no_class_is_both_indexed_and_declared_missing(self) -> None:
        overlap = sorted(set(INDEXED_ATTRIBUTES) & set(MISSING_INDEXED_CLASSES))
        self.assertEqual(overlap, [], "a class cannot be both done and not done")

    def test_every_missing_class_is_one_the_vocabulary_declares(self) -> None:
        for intervention_class in MISSING_INDEXED_CLASSES:
            with self.subTest(intervention_class=intervention_class):
                self.assertIn(intervention_class, intervention_classes())

    def test_every_missing_class_says_what_choosing_its_columns_would_take(self) -> None:
        """A gap with no reason is indistinguishable from an oversight."""
        for intervention_class, reason in MISSING_INDEXED_CLASSES.items():
            with self.subTest(intervention_class=intervention_class):
                self.assertGreater(len(reason.split()), 12, intervention_class)

    def test_every_class_with_attributes_is_either_indexed_or_declared_missing(self) -> None:
        """No class falls through silently.

        `monoclonal_antibody` is in the intervention vocabulary and has no attributes at
        all, so there is nothing to index and nothing to declare missing - which is why
        the set under test is classes that *have* attributes.
        """
        for intervention_class in sorted(intervention_classes()):
            if not attribute_definitions(intervention_class):
                continue
            with self.subTest(intervention_class=intervention_class):
                self.assertTrue(
                    intervention_class in INDEXED_ATTRIBUTES
                    or intervention_class in MISSING_INDEXED_CLASSES,
                    f"{intervention_class} has attributes but no decision either way",
                )

    def test_asking_for_an_unindexed_class_says_why(self) -> None:
        with self.assertRaises(LookupError) as caught:
            indexed_attributes("drug")
        self.assertIn("28 attributes", str(caught.exception))


class QuantityTest(unittest.TestCase):
    """Parsed from the document's own words, never converted, and never guessed."""

    def test_a_plain_duration_parses(self) -> None:
        self.assertEqual(parse_quantity("24 months", "duration"), (24.0, "months"))

    def test_a_qualifier_does_not_block_the_parse(self) -> None:
        """The qualifier is what `bound` records; it is not part of the quantity."""
        self.assertEqual(parse_quantity("at least 24 months", "duration"), (24.0, "months"))

    def test_the_parser_never_converts(self) -> None:
        """"2 years" is not 24 months.

        Canonicalising would make two documents group and would also put a number in the
        corpus that neither wrote - a month is 28 to 31 days, so the conversion is not
        even exact. The document's words stay authoritative.
        """
        self.assertEqual(parse_quantity("2 years", "duration"), (2.0, "years"))

    def test_a_range_parses_as_nothing(self) -> None:
        """It has no single magnitude, and taking an end would be a claim nobody made."""
        self.assertEqual(parse_quantity("24 to 36 months", "duration"), (None, ""))
        self.assertEqual(parse_quantity("24-36 months", "duration"), (None, ""))

    def test_a_second_number_of_another_kind_does_not_confuse_the_parse(self) -> None:
        """"24 months at 2-8C" is a shelf life of 24 months.

        The temperature is not a duration, so the duration scan sees one candidate. This
        is why the kind is declared per column rather than sniffed from the text.
        """
        self.assertEqual(parse_quantity("24 months at 2-8C", "duration"), (24.0, "months"))

    def test_the_declared_kind_decides_what_is_read(self) -> None:
        """The same characters are a duration under one column and nothing under another."""
        self.assertEqual(parse_quantity("24 months", "count"), (None, ""))
        self.assertEqual(parse_quantity("24 months", "currency"), (None, ""))

    def test_a_count_written_as_a_word_parses(self) -> None:
        """Otherwise the column would split by prose style rather than by dose count."""
        self.assertEqual(parse_quantity("two doses", "count"), (2.0, "doses"))
        self.assertEqual(parse_quantity("a two-dose schedule", "count"), (2.0, "doses"))

    def test_a_dosing_interval_does_not_become_the_dose_count(self) -> None:
        self.assertEqual(parse_quantity("2 doses, 4 weeks apart", "count"), (2.0, "doses"))

    def test_currency_parses_either_side_of_the_number(self) -> None:
        self.assertEqual(parse_quantity("$1.50 per dose", "currency"), (1.5, "usd"))
        self.assertEqual(parse_quantity("3.50 USD per dose", "currency"), (3.5, "usd"))

    def test_a_price_range_parses_as_nothing(self) -> None:
        self.assertEqual(parse_quantity("$1.50-$3.00", "currency"), (None, ""))

    def test_a_column_declaring_no_quantity_parses_nothing(self) -> None:
        """`presentation` says "10-dose vial"; reading 10 out of it would say it is ten."""
        self.assertEqual(parse_quantity("10-dose vial", ""), (None, ""))

    def test_a_compound_presentation_parses_as_nothing_under_a_duration(self) -> None:
        self.assertEqual(
            parse_quantity("lyophilized, 10-dose vial", "duration"), (None, "")
        )


class DecouplingTest(unittest.TestCase):
    def test_archivist_imports_nothing_from_scout_or_searcher(self) -> None:
        """Its resemblance to them is superficial and must stay that way.

        Both read documents and both cite blocks, but Scout judges a target against
        outside evidence and Archivist judges nothing. Sharing a type would make one
        tool's concept of a verdict, a ledger, or a query facet leak into a tool that has
        none of those things.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "services" / "archivist"
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("services.scout", "services.searcher"):
                if forbidden in text:
                    offenders.append(f"{path.name} imports {forbidden}")
        self.assertEqual(offenders, [])

    def test_archivist_does_not_borrow_another_tool_s_nouns(self) -> None:
        """`facet` is Searcher's and `ledger` is Scout's.

        Sharing a noun for a different mechanism is how two unrelated things come to look
        like one. A `QueryFacets` is a set of fields sent to a retrieval provider; a
        filter over a static table is not that.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "services" / "archivist"
        offenders = []
        for path in root.rglob("*.py"):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                lowered = line.lower()
                # The one permitted mention is the comment in `query.py` explaining why
                # the noun is not borrowed.
                if "queryfacets" in lowered:
                    continue
                for noun in ("facet", "ledger"):
                    if noun in lowered:
                        offenders.append(f"{path.name}:{number} uses {noun!r}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
