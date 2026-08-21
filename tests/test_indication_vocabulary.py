"""A context tag is a key and a search term at once.

It is stamped on every block and result, and it is also substituted into retrieval
prompts and joined into query text. Those two jobs pull in opposite directions the
moment a name has more than one word, and the vocabulary lost that argument twice:
Group B Streptococcus became `gbs`, which in a vaccine context also means
Guillain-Barre Syndrome, and tuberculosis became `tb`, which means very little.

Both tags that name subject matter are covered here, because the intervention class
had the identical fault and it was not obvious: it reads as a label in the rail, but
it is also interpolated into eight prompt sentences and joined into the fallback query
beside the indication, and it reached both as `mab`.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from shared.vocabulary import indications_for, intervention_classes, search_term

ROOT = Path(__file__).resolve().parents[1]
VOCAB = ROOT / "shared" / "indications.yaml"
SERVICES = ROOT / "services"


#: Classes whose indication set is narrower than every other non-vaccine class, and the
#: question that raises.
#:
#: `drug`, `diagnostic` and `monoclonal_antibody` all declare exactly malaria, HIV and
#: tuberculosis. `device` declares malaria alone, while carrying a full set of Inspector
#: and Scout configs - so a device run can only ever be about malaria however the
#: document is written.
#:
#: Recorded rather than filled in. Which indications a class serves is a statement about
#: the portfolio, and nothing in this repository states it: the device configs describe
#: how to judge a device and never name a disease. Inventing two entries here would put
#: an unsourced claim about the portfolio into the vocabulary every output is stamped
#: with.
NARROWER_THAN_PEERS = {
    "device": "declares malaria alone where drug, diagnostic and monoclonal_antibody share malaria, HIV and tuberculosis",
}

#: What the non-vaccine classes share, and the baseline `NARROWER_THAN_PEERS` is measured
#: against. Vaccine is deliberately excluded: its set is a superset, which is a portfolio
#: fact rather than an inconsistency.
PEER_BASELINE = ("malaria", "hiv", "tuberculosis")


def _configured_intervention_classes() -> set[str]:
    """Classes a tool can actually be run for, read from the config filenames.

    `bmgf_<source_type>_<intervention_class>.yaml`, and the class may itself contain an
    underscore, so it is everything after the second one.
    """
    classes: set[str] = set()
    for service in ("inspector", "scout"):
        for config in (SERVICES / service / "configs").glob("bmgf_*.yaml"):
            parts = config.stem.split("_", 2)
            if len(parts) == 3:
                classes.add(parts[2])
    return classes


class CoverageTests(unittest.TestCase):
    """A class a tool can be run for needs indications, or the run cannot be configured."""

    def test_every_configured_class_has_at_least_one_indication(self) -> None:
        for intervention_class in sorted(_configured_intervention_classes()):
            with self.subTest(intervention_class=intervention_class):
                self.assertTrue(
                    indications_for(intervention_class),
                    f"{intervention_class} has configs but no indication, so its "
                    "dropdown is empty and no run can be started",
                )

    def test_every_declared_class_is_one_a_tool_can_run(self) -> None:
        """An indication set for a class with no config is a dropdown to nowhere."""
        configured = _configured_intervention_classes()
        self.assertEqual(sorted(intervention_classes() - configured), [])

    def test_the_peer_baseline_is_what_the_peers_actually_share(self) -> None:
        """So the baseline cannot drift from the file it describes."""
        peers = [
            intervention_class
            for intervention_class in intervention_classes()
            if intervention_class not in {"vaccine"} | set(NARROWER_THAN_PEERS)
        ]
        self.assertTrue(peers)
        for intervention_class in peers:
            with self.subTest(intervention_class=intervention_class):
                self.assertEqual(
                    sorted(indications_for(intervention_class)), sorted(PEER_BASELINE)
                )

    def test_a_narrower_class_is_still_narrower(self) -> None:
        for intervention_class in NARROWER_THAN_PEERS:
            with self.subTest(intervention_class=intervention_class):
                self.assertLess(
                    len(indications_for(intervention_class)), len(PEER_BASELINE)
                )

    def test_a_class_that_caught_up_leaves_the_list(self) -> None:
        """So the note cannot outlive the gap and understate what a run can cover."""
        stale = [
            intervention_class
            for intervention_class in NARROWER_THAN_PEERS
            if len(indications_for(intervention_class)) >= len(PEER_BASELINE)
        ]
        self.assertEqual(stale, [])

    def test_vaccine_is_a_superset_of_the_baseline(self) -> None:
        """A broader set is a portfolio fact; a set missing the baseline is a gap."""
        self.assertLessEqual(set(PEER_BASELINE), set(indications_for("vaccine")))


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


class InterventionClassTests(unittest.TestCase):
    """The class is the other tag that becomes text, so it obeys the same rule."""

    def test_every_class_reads_as_a_search_term(self) -> None:
        for name in intervention_classes():
            self.assertRegex(name, r"^[a-z0-9]+(_[a-z0-9]+)*$", name)
            self.assertNotIn("_", search_term(name), name)

    def test_no_class_is_an_acronym_a_search_would_miss(self) -> None:
        """`mab` retrieves little; the literature says monoclonal antibody."""
        classes = intervention_classes()
        self.assertNotIn("mab", classes)
        self.assertIn("monoclonal_antibody", classes)

    def test_the_text_form_is_derived_from_the_tag_not_stored(self) -> None:
        """A stored second spelling could disagree with the key it was selected by."""
        from services.inspector.models import find_config as inspector_config
        from services.scout.models import ScoutTypeConfig

        config = inspector_config("bmgf", "itpp", "monoclonal_antibody")
        self.assertEqual(config.intervention_class, "monoclonal_antibody")
        self.assertEqual(config.intervention_term, "monoclonal antibody")
        self.assertEqual(
            ScoutTypeConfig(
                type_key="k",
                org="bmgf",
                source_type="itpp",
                intervention_class="monoclonal_antibody",
                display_name="d",
                query_extraction_guidance="g",
                sources=["s"],
            ).intervention_term,
            "monoclonal antibody",
        )

    def test_no_prompt_interpolates_the_raw_tag(self) -> None:
        """The tag selects configuration; only `intervention_term` may be read aloud.

        A scan rather than a review because the two are one word apart, the wrong one
        is what a stage already has in scope, and nothing about the result looks broken
        - a query simply carries `monoclonal_antibody` and retrieves less.
        """
        offenders = [
            f"{path.relative_to(ROOT)}:{number}"
            for path in SERVICES.rglob("*.py")
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
            if "{config.intervention_class}" in line
        ]
        self.assertEqual(offenders, [], "read config.intervention_term in prose")


class SearchTermTests(unittest.TestCase):
    def test_a_single_word_tag_is_unchanged(self) -> None:
        self.assertEqual(search_term("malaria"), "malaria")

    def test_underscores_become_spaces(self) -> None:
        self.assertEqual(
            search_term("group_b_streptococcus"), "group b streptococcus"
        )


if __name__ == "__main__":
    unittest.main()
