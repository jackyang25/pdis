"""The corpus substrate: what a row may say, and what the grid as a whole must hold.

These are the invariants that make the artifact trustworthy without anyone re-reading the
source documents. The source documents are BMGF product files and are not in this
repository, so the usual test for a generated artifact - regenerate it and diff - cannot
run. What runs instead is every rule the build enforced, re-checked on load, which is the
stronger guarantee for the actual risk: a file people edit by hand during review.

The provenance chain is the centre of it. `stated` sits inside `quote`, which sits inside
`block_text`, and each link closes a different failure - a fabricated sentence, and a
paraphrase of a real one.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.archivist import (
    CORPUS_VERSION,
    Corpus,
    CorpusDocument,
    CorpusRecord,
    indexed_attributes,
    load_corpus,
    write_corpus,
)
from services.archivist.corpus_store import CORPUS_FILE

VACCINE_COLUMNS = [column.attribute for column in indexed_attributes("vaccine")]


def document(document_id: str = "d1", **overrides) -> CorpusDocument:
    fields = dict(
        id=document_id,
        title=f"Profile {document_id}",
        org="bmgf",
        intervention_class="vaccine",
        indication="malaria",
        source_type="itpp",
    )
    fields.update(overrides)
    return CorpusDocument(**fields)


def silent_grid(document_id: str = "d1") -> tuple[CorpusRecord, ...]:
    """A complete grid in which the document specified nothing."""
    return tuple(
        CorpusRecord(
            document_id=document_id,
            attribute=attribute,
            status="not_stated",
            reason="not specified",
        )
        for attribute in VACCINE_COLUMNS
    )


def value(document_id: str = "d1", **overrides) -> CorpusRecord:
    fields = dict(
        document_id=document_id,
        attribute="vaccine.shelf_life",
        status="stated",
        bound="minimum",
        stated="24 months",
        magnitude=24.0,
        unit="months",
        quote="stable for at least 24 months",
        block_text="The vaccine must remain stable for at least 24 months at 2-8C.",
        block_id="b-0042",
        section_label="stability",
    )
    fields.update(overrides)
    return CorpusRecord(**fields)


class ProvenanceChainTest(unittest.TestCase):
    """`stated` inside `quote` inside `block_text`, or the row is refused."""

    def test_a_quote_the_block_does_not_contain_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            value(quote="proven to last 24 months")
        self.assertIn("does not appear in the block", str(caught.exception))

    def test_a_value_that_paraphrases_its_own_quote_is_refused(self) -> None:
        """The guard against the most likely wrong answer, not the least likely.

        A model asked for a shelf life will answer "about two years" from a document that
        wrote "24 months". The quote is genuine, so a verbatim check on the quote alone
        passes it, and the archive then quotes a number nobody wrote.
        """
        with self.assertRaises(ValueError) as caught:
            value(stated="about two years", magnitude=None, unit="")
        self.assertIn("not a span of the quote", str(caught.exception))

    def test_a_value_with_no_quote_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            value(quote="", block_text="", block_id="")

    def test_a_verified_value_is_accepted(self) -> None:
        self.assertEqual(value().stated, "24 months")


class SilenceTest(unittest.TestCase):
    """A document that said nothing is a row, and a row that says so and nothing else."""

    def test_silence_carries_no_value_and_no_quote(self) -> None:
        with self.assertRaises(ValueError):
            CorpusRecord(
                document_id="d1",
                attribute="vaccine.shelf_life",
                status="not_stated",
                stated="24 months",
            )

    def test_silence_may_explain_itself(self) -> None:
        record = CorpusRecord(
            document_id="d1",
            attribute="vaccine.shelf_life",
            status="not_stated",
            reason="The stability section gives a storage range and no shelf life.",
        )
        self.assertEqual(record.status, "not_stated")

    def test_a_stated_value_may_not_explain_itself_in_prose(self) -> None:
        """Its quote is its justification. A second one could disagree with the first."""
        with self.assertRaises(ValueError) as caught:
            value(reason="the document seems to imply this")
        self.assertIn("explains itself with its quote", str(caught.exception))


class UncertaintyTest(unittest.TestCase):
    """The one status that may carry a value or none, because the doubt has two shapes."""

    def test_uncertain_may_carry_a_candidate_value(self) -> None:
        record = value(status="uncertain", reason="may be a storage temperature")
        self.assertEqual(record.status, "uncertain")
        self.assertEqual(record.stated, "24 months")

    def test_uncertain_may_carry_no_value_at_all(self) -> None:
        record = CorpusRecord(
            document_id="d1",
            attribute="vaccine.shelf_life",
            status="uncertain",
            reason="The model returned no reading.",
        )
        self.assertEqual(record.stated, "")


class ConditionTest(unittest.TestCase):
    """A condition is typed and quoted, or it is not recorded.

    A free-text note would accept anything, which is the failure a closed reference to a
    real attribute is here to prevent.
    """

    def test_half_a_condition_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            value(condition_attribute="vaccine.presentation")
        self.assertIn("needs both", str(caught.exception))

    def test_a_condition_the_block_does_not_state_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            value(condition_attribute="vaccine.presentation", condition_stated="liquid")
        self.assertIn("not stated in the block", str(caught.exception))

    def test_a_condition_naming_no_real_attribute_is_refused(self) -> None:
        record = value(
            condition_attribute="vaccine.not_an_attribute",
            condition_stated="2-8C",
        )
        with self.assertRaises(ValueError) as caught:
            Corpus(
                documents=(document(),),
                records=tuple(
                    record if r.attribute == record.attribute else r for r in silent_grid()
                ),
            )
        self.assertIn("not an attribute of vaccine", str(caught.exception))

    def test_a_condition_may_name_an_attribute_that_is_not_a_column(self) -> None:
        """A value can turn on geography, which the corpus does not index as a column.

        The set a condition may name is every attribute of the class, not the eight
        columns: narrowing it to the columns would make a real conditional value
        unrecordable.
        """
        record = value(
            condition_attribute="vaccine.target_countries",
            condition_stated="Gavi-eligible countries",
            block_text=(
                "The vaccine must remain stable for at least 24 months in "
                "Gavi-eligible countries."
            ),
        )
        corpus = Corpus(
            documents=(document(),),
            records=tuple(
                record if r.attribute == record.attribute else r for r in silent_grid()
            ),
        )
        self.assertEqual(len(corpus.records), len(VACCINE_COLUMNS))


class GridTest(unittest.TestCase):
    """The corpus is a grid, not a list of hits."""

    def test_a_missing_row_is_refused(self) -> None:
        """Because a hole reads as silence and means "we never found out".

        The whole reason silence is recorded is so "eleven of twelve never specified this"
        is answerable. A sparse corpus makes that indistinguishable from "we only read
        one document".
        """
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=silent_grid()[:-1])
        self.assertIn("sparse", str(caught.exception))

    def test_two_answers_to_the_same_question_are_refused(self) -> None:
        grid = silent_grid()
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=grid + (grid[0],))
        self.assertIn("same question", str(caught.exception))

    def test_a_minimum_and_an_optimal_are_two_questions_not_one(self) -> None:
        rest = tuple(r for r in silent_grid() if r.attribute != "vaccine.shelf_life")
        corpus = Corpus(
            documents=(document(),),
            records=rest
            + (
                value(bound="minimum"),
                value(
                    bound="optimal",
                    stated="36 months",
                    magnitude=36.0,
                    quote="optimally 36 months",
                    block_text=(
                        "The vaccine must remain stable for at least 24 months, "
                        "optimally 36 months."
                    ),
                ),
            ),
        )
        self.assertEqual(len(corpus.records), len(VACCINE_COLUMNS) + 1)

    def test_a_record_citing_an_unlisted_document_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=silent_grid("other"))
        self.assertIn("does not list", str(caught.exception))

    def test_a_document_listed_twice_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Corpus(documents=(document(), document()), records=silent_grid())


class ColumnVocabularyTest(unittest.TestCase):
    """A row answers a declared column, in that column's declared vocabulary."""

    def test_an_attribute_that_is_not_a_column_is_refused(self) -> None:
        rows = silent_grid() + (
            CorpusRecord(document_id="d1", attribute="vaccine.efficacy", status="not_stated"),
        )
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=rows)
        self.assertIn("not a corpus column", str(caught.exception))

    def test_a_tag_outside_the_declared_vocabulary_is_refused(self) -> None:
        # A `not_stated` row cannot carry tags at all, so the stray tag has to ride on a
        # stated one to reach the corpus-level check.
        rows = tuple(
            row for row in silent_grid() if row.attribute != "vaccine.target_population"
        ) + (
            value(
                attribute="vaccine.target_population",
                stated="infants",
                magnitude=None,
                unit="",
                quote="infants aged 6-14 weeks",
                block_text="Target: infants aged 6-14 weeks.",
                tags=("toddlers",),
            ),
        )
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=rows)
        self.assertIn("outside the declared vocabulary", str(caught.exception))

    def test_a_tag_on_a_column_that_is_read_rather_than_filtered_is_refused(self) -> None:
        rows = tuple(r for r in silent_grid() if r.attribute != "vaccine.shelf_life") + (
            value(tags=("infants",)),
        )
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=rows)
        self.assertIn("outside the declared vocabulary", str(caught.exception))

    def test_a_magnitude_on_a_column_declaring_no_quantity_is_refused(self) -> None:
        """`presentation` says "10-dose vial"; parsing that to 10 would say it is ten."""
        rows = tuple(r for r in silent_grid() if r.attribute != "vaccine.presentation") + (
            value(
                attribute="vaccine.presentation",
                stated="10-dose vial",
                magnitude=10.0,
                unit="doses",
                quote="a 10-dose vial",
                block_text="Supplied as a 10-dose vial.",
            ),
        )
        with self.assertRaises(ValueError) as caught:
            Corpus(documents=(document(),), records=rows)
        self.assertIn("declares no quantity", str(caught.exception))

    def test_a_magnitude_with_no_unit_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            value(unit="")


class HeaderTest(unittest.TestCase):
    """The manifest half of a document, validated against the shared vocabulary."""

    def test_an_unknown_intervention_class_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            document(intervention_class="widget")

    def test_an_indication_the_class_does_not_declare_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            document(indication="ebola")
        self.assertIn("not an indication declared", str(caught.exception))


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "corpus.json"
        self.corpus = Corpus(
            documents=(document(),),
            records=tuple(r for r in silent_grid() if r.attribute != "vaccine.shelf_life")
            + (value(),),
            built_at="2026-08-23T00:00:00+00:00",
        )
        write_corpus(self.corpus, self.path)

    def test_a_written_corpus_reads_back_identically(self) -> None:
        loaded = load_corpus(self.path)
        self.assertEqual(loaded.built_at, self.corpus.built_at)
        self.assertEqual(len(loaded.records), len(self.corpus.records))
        self.assertEqual(loaded.document("d1").title, "Profile d1")

    def test_an_absent_corpus_is_empty_rather_than_an_error(self) -> None:
        """The tool is registered before any archive is built.

        "Nothing has been indexed yet" is a state the interface must be able to show;
        raising here would make the page fail instead of explain.
        """
        missing = Path(tempfile.mkdtemp()) / "none.json"
        self.assertEqual(load_corpus(missing).documents, ())

    def test_a_hand_edited_quote_does_not_survive_a_load(self) -> None:
        """The reason loading re-validates rather than trusting the file.

        This is the realistic failure: a reviewer improves the wording of a quote, and the
        row stops being evidence of anything.
        """
        raw = json.loads(self.path.read_text())
        for row in raw["records"]:
            if row["quote"]:
                row["quote"] = "stable for at least 24 calendar months"
        self.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.path)
        self.assertIn("does not appear in the block", str(caught.exception))

    def test_an_unknown_field_is_refused_rather_than_dropped(self) -> None:
        raw = json.loads(self.path.read_text())
        raw["records"][0]["reviewer_note"] = "looks right to me"
        self.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.path)
        self.assertIn("unknown fields", str(caught.exception))

    def test_an_older_version_is_refused_rather_than_read_optimistically(self) -> None:
        raw = json.loads(self.path.read_text())
        raw["version"] = CORPUS_VERSION - 1
        self.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.path)
        self.assertIn("Rebuild it", str(caught.exception))

    def test_rows_are_written_in_a_stable_order(self) -> None:
        """So a rebuild that changed one reading produces a one-row diff.

        Review happens in that diff. A reshuffled file makes it unreadable.
        """
        first = self.path.read_text()
        write_corpus(load_corpus(self.path), self.path)
        self.assertEqual(first, self.path.read_text())


class CommittedArtifactTest(unittest.TestCase):
    def test_the_committed_corpus_satisfies_every_invariant(self) -> None:
        """Turns on the day a build lands, and asserts everything above about it.

        Skipped rather than passed vacuously while no corpus is committed: a test that
        silently checks nothing is worse than one that says it checked nothing.
        """
        if not CORPUS_FILE.exists():
            self.skipTest("no corpus has been built and committed yet")
        corpus = load_corpus()
        self.assertTrue(corpus.documents, "a committed corpus with no documents")
        self.assertTrue(corpus.built_at, "a committed corpus with no build timestamp")


if __name__ == "__main__":
    unittest.main()
