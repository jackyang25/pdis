"""An attribute's name as words a search provider can use.

An attribute is named `vaccine.duration_of_protection`: a namespace, a dot, and words joined
by underscores. Two places dropped that into search text after replacing only the
underscores, so the namespace and the dot went to the provider:

    hiv vaccine vaccine.duration of protection Annualized relapse/rebound rate ...

No provider knows what `vaccine.duration` is, and the prefix repeats the intervention class
that is already the word before it. The two places were the numeric fallback query in
`query_extractor` and `RetrievalIntent.topic`, which six source adapters fall back to when a
query carries no text of its own.
"""

import unittest

from shared.vocabulary import searchable_attribute_phrase


class SearchableAttributePhraseTests(unittest.TestCase):
    def test_the_namespace_is_dropped(self):
        """The bug. `vaccine.` repeats the intervention class already in the query."""
        self.assertEqual(
            searchable_attribute_phrase("vaccine.duration_of_protection"),
            "duration of protection",
        )

    def test_underscores_become_spaces(self):
        self.assertEqual(
            searchable_attribute_phrase("drug.target_affordable_pricing_procurement"),
            "target affordable pricing procurement",
        )

    def test_a_hyphen_is_a_separator_too(self):
        """Refs are generated from document headings, which carry hyphens as often as not."""
        self.assertEqual(searchable_attribute_phrase("device.storage-temp"), "storage temp")

    def test_a_name_with_no_namespace_is_left_whole(self):
        """Not every ref is namespaced, and the last dot-segment of one word is that word."""
        self.assertEqual(searchable_attribute_phrase("efficacy"), "efficacy")
        self.assertEqual(searchable_attribute_phrase("no_namespace_here"), "no namespace here")

    def test_only_the_last_segment_survives_a_deeper_namespace(self):
        self.assertEqual(searchable_attribute_phrase("a.b.c_d"), "c d")

    def test_the_result_carries_no_dot(self):
        """The property that matters: whatever comes in, no provider sees a dotted token."""
        for name in (
            "vaccine.duration_of_protection",
            "drug.efficacy",
            "a.b.c",
            "no_namespace",
        ):
            self.assertNotIn(".", searchable_attribute_phrase(name), name)

    def test_surrounding_space_is_not_carried_into_a_query(self):
        """A phrase is joined with others by a space, so a stray one doubles up."""
        self.assertEqual(searchable_attribute_phrase("  drug.efficacy  "), "efficacy")

    def test_an_empty_name_yields_an_empty_phrase(self):
        """Rather than a lone dot or a space, either of which would reach a provider."""
        self.assertEqual(searchable_attribute_phrase(""), "")


if __name__ == "__main__":
    unittest.main()


class NoRawRefReachesAProviderTests(unittest.TestCase):
    """The two call sites, asserted so a third cannot be added by hand.

    A grep test rather than a behavioural one, because the failure mode is someone writing
    `attribute.name.replace("_", " ")` again: correct-looking, and wrong in exactly the way
    that took the namespace to a search provider.
    """

    FILES = (
        "services/scout/stages/query_extractor.py",
        "services/scout/stages/intent_builder.py",
    )

    def test_no_query_builder_normalises_a_ref_by_hand(self):
        import pathlib

        offenders = []
        for name in self.FILES:
            text = pathlib.Path(name).read_text()
            for line in text.split("\n"):
                if "replace(" not in line or "attribute" not in line:
                    continue
                if line.strip().startswith(("#", "*")):
                    continue
                offenders.append(f"{name}: {line.strip()}")
        self.assertEqual(offenders, [], "use searchable_attribute_phrase")

    def test_both_call_sites_use_the_shared_phrase(self):
        import pathlib

        for name in self.FILES:
            text = pathlib.Path(name).read_text()
            self.assertIn("searchable_attribute_phrase", text, name)
