"""What the extractor keeps, what it discards, and what it never asks the model for.

Every check here fails closed. An unverifiable reading leaves no row, and the caller turns
"nothing survived" into a flagged `uncertain` row - a worse outcome for recall and the only
safe one for a corpus that gets quoted back to partners.

Three things are deliberately not asked of the model, and each has a test: the block id
(found from the quote, so a quote and an id can never disagree), the magnitude (parsed in
code, so it cannot differ from the document's number), and the tag (a separate stage, so
the vocabulary can grow without re-reading fifty documents).
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from services.archivist import Corpus, CorpusDocument, indexed_attributes
from services.archivist.stages.classifier import classify_records
from services.archivist.stages.extractor import (
    build_attribute_instructions,
    build_document_text,
    build_system_prompt,
    extract_document,
    extraction_schema,
    prepare_document,
)
from shared.vocabulary import attribute_definitions

COLUMNS = [column.attribute for column in indexed_attributes("vaccine")]
LOCAL = [attribute.split(".", 1)[1] for attribute in COLUMNS]


@dataclass
class Block:
    """The fields the extractor reads off a chunker block."""

    id: str
    content: str
    section_label: str = ""
    heading_stack: list = field(default_factory=list)


BLOCKS = [
    Block("b1", "Shelf life: minimum 24 months at 2-8C; optimal 36 months.", "stability",
          ["Product Characteristics"]),
    Block("b2", "Presentation: 10-dose lyophilized vial.", "presentation",
          ["Product Characteristics"]),
    Block("b3", "Target population: infants aged 6-14 weeks receiving routine EPI "
                "vaccination.", "population", ["Clinical"]),
    Block("b4", "Storage at 2-8C is required throughout distribution.", "stability",
          ["Product Characteristics"]),
]

DOCUMENT = CorpusDocument(
    id="d1",
    title="Malaria Vaccine iTPP",
    org="bmgf",
    intervention_class="vaccine",
    indication="malaria",
    source_type="itpp",
)

SILENT = {"status": "not_stated", "reason": "not specified anywhere", "values": []}


def stated(*values) -> dict:
    return {"status": "stated", "reason": "", "values": list(values)}


def one(
    stated_text: str,
    quote: str,
    *,
    bound: str = "single",
    condition_attribute: str = "",
    condition_stated: str = "",
) -> dict:
    return {
        "bound": bound,
        "stated": stated_text,
        "quote": quote,
        "condition_attribute": condition_attribute,
        "condition_stated": condition_stated,
    }


class Client:
    """Answers per attribute, so one call can be given a different reading from another."""

    def __init__(self, answers: dict, default=None):
        self.answers = answers
        self.default = default if default is not None else SILENT
        self.calls: list[str] = []
        self.prompts: list[tuple[str, str]] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        attribute = user_message.rsplit("Read `", 1)[1].split("`")[0]
        self.calls.append(attribute)
        self.prompts.append((system_prompt, user_message))
        return self.answers.get(attribute, self.default)


class RequestShapeTest(unittest.TestCase):
    def test_one_call_per_attribute(self) -> None:
        """Eight independent readings, not one prompt asking for eight.

        A model that has just found a shelf life is readier to read the next sentence as a
        thermostability regime. The suite applies this rule wherever a decision is per
        item, and each column is a per-item decision.
        """
        client = Client({})
        extract_document(DOCUMENT, BLOCKS, client)
        self.assertEqual(sorted(client.calls), sorted(LOCAL))

    def test_the_document_precedes_the_attribute_in_every_request(self) -> None:
        """What makes the eight calls share a cached prefix.

        The system prompt is constant and the document is the head of the user message, so
        only the last few hundred words differ between the eight. Reversed, a document
        would be charged as new input eight times.
        """
        client = Client({})
        extract_document(DOCUMENT, BLOCKS, client)
        systems = {system for system, _ in client.prompts}
        self.assertEqual(len(systems), 1, "the constant half of the prompt is not constant")
        for _, message in client.prompts:
            self.assertLess(
                message.index("Shelf life:"),
                message.index("THE ATTRIBUTE TO READ"),
                "the attribute comes before the document, so nothing is cacheable",
            )

    def test_the_fence_quotes_the_vocabulary_s_own_words(self) -> None:
        """Not a paraphrase of them, so the two cannot drift apart."""
        definitions = {d.name: d for d in attribute_definitions("vaccine")}
        text = build_attribute_instructions(
            indexed_attributes("vaccine")[5], definitions
        )
        self.assertIn(
            " ".join(definitions["vaccine.thermostability"].description.split()), text
        )

    def test_a_block_carries_its_section_and_heading_path(self) -> None:
        """Without them a table row reading "24 months | 36 months" is unreadable.

        The bound is unanswerable without the row's heading, and which attribute the row
        is about is unanswerable without the section.
        """
        text = build_document_text(BLOCKS)
        self.assertIn("section: stability", text)
        self.assertIn("under: Product Characteristics", text)

    def test_the_schema_enumerates_every_attribute_of_the_class_as_a_condition(self) -> None:
        """One vocabulary on both ends of the wire.

        `Corpus` validates a condition against every attribute of the class, so the schema
        offers the same set. A hand-picked shortlist would be invented content and would
        make a real conditional value unrecordable.
        """
        conditions = extraction_schema("vaccine")["properties"]["values"]["items"][
            "properties"
        ]["condition_attribute"]["enum"]
        self.assertIn("", conditions)
        self.assertIn("vaccine.target_countries", conditions)
        self.assertEqual(
            len(conditions), len(attribute_definitions("vaccine")) + 1
        )

    def test_the_rules_prompt_names_silence_as_a_correct_answer(self) -> None:
        """Given no way to say nothing was stated, a model states something."""
        self.assertIn("common and correct answer", build_system_prompt())


class VerificationTest(unittest.TestCase):
    def test_a_fabricated_quote_leaves_no_value(self) -> None:
        client = Client(
            {"shelf_life": stated(one("24 months", "guaranteed stable for 24 months"))}
        )
        records, report = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"]
        self.assertEqual([r.status for r in shelf], ["uncertain"])
        self.assertEqual(shelf[0].stated, "")
        self.assertEqual(report.unverified, 1)

    def test_a_paraphrase_of_a_real_quote_leaves_no_value(self) -> None:
        """The likeliest wrong answer, and the one a quote check alone would pass."""
        client = Client(
            {"shelf_life": stated(one("about two years", "minimum 24 months at 2-8C"))}
        )
        records, report = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"]
        self.assertEqual([r.status for r in shelf], ["uncertain"])
        self.assertEqual(report.paraphrased, 1)

    def test_a_verified_value_keeps_its_block_and_section(self) -> None:
        client = Client({"shelf_life": stated(one("24 months", "minimum 24 months"))})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual(shelf.status, "stated")
        self.assertEqual(shelf.block_id, "b1")
        self.assertEqual(shelf.section_label, "stability")

    def test_the_block_is_found_from_the_quote_rather_than_asked_for(self) -> None:
        """So a quote from one block and an id from another cannot disagree.

        Nothing in the wire contract names a block at all.
        """
        properties = extraction_schema("vaccine")["properties"]["values"]["items"][
            "properties"
        ]
        self.assertNotIn("block_id", properties)


class BoundTest(unittest.TestCase):
    def test_a_minimum_and_an_optimal_become_two_rows(self) -> None:
        """A TPP prints both side by side, and they are different claims."""
        client = Client(
            {
                "shelf_life": stated(
                    one("24 months", "minimum 24 months", bound="minimum"),
                    one("36 months", "optimal 36 months", bound="optimal"),
                )
            }
        )
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"]
        self.assertEqual([r.bound for r in shelf], ["minimum", "optimal"])
        self.assertEqual([r.magnitude for r in shelf], [24.0, 36.0])

    def test_the_same_bound_answered_twice_keeps_one_row(self) -> None:
        """`Corpus` would refuse the pair; dropping it here keeps the reason in the report."""
        client = Client(
            {
                "shelf_life": stated(
                    one("24 months", "minimum 24 months", bound="minimum"),
                    one("24 months", "minimum 24 months", bound="minimum"),
                )
            }
        )
        records, report = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"]
        self.assertEqual(len(shelf), 1)
        self.assertTrue(any("repeat reading" in note for note in report.notes))


class QuantityAtExtractionTest(unittest.TestCase):
    def test_the_magnitude_is_parsed_from_the_document_s_words(self) -> None:
        """Never retyped by the model, which is why the wire contract has no number."""
        properties = extraction_schema("vaccine")["properties"]["values"]["items"][
            "properties"
        ]
        self.assertNotIn("magnitude", properties)
        client = Client({"shelf_life": stated(one("24 months", "minimum 24 months"))})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual((shelf.magnitude, shelf.unit), (24.0, "months"))

    def test_a_column_declaring_no_quantity_gets_no_magnitude(self) -> None:
        client = Client(
            {"presentation": stated(one("10-dose lyophilized vial", "10-dose lyophilized vial"))}
        )
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        row = [r for r in records if r.attribute == "vaccine.presentation"][0]
        self.assertIsNone(row.magnitude)
        self.assertEqual(row.stated, "10-dose lyophilized vial")


class ConditionAtExtractionTest(unittest.TestCase):
    def test_a_condition_the_block_does_not_state_is_dropped_and_the_value_kept(self) -> None:
        """The value is unaffected by a bad condition, so refusing both would lose data."""
        client = Client(
            {
                "shelf_life": stated(
                    one(
                        "24 months",
                        "minimum 24 months",
                        condition_attribute="vaccine.presentation",
                        condition_stated="liquid formulation",
                    )
                )
            }
        )
        records, report = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual(shelf.stated, "24 months")
        self.assertEqual(shelf.condition_attribute, "")
        self.assertTrue(any("dropped the condition" in note for note in report.notes))

    def test_a_condition_naming_no_real_attribute_is_dropped(self) -> None:
        client = Client(
            {
                "shelf_life": stated(
                    one(
                        "24 months",
                        "minimum 24 months at 2-8C",
                        condition_attribute="vaccine.storage",
                        condition_stated="2-8C",
                    )
                )
            }
        )
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual(shelf.condition_attribute, "")

    def test_a_condition_stated_in_the_citing_block_survives(self) -> None:
        client = Client(
            {
                "shelf_life": stated(
                    one(
                        "24 months",
                        "minimum 24 months at 2-8C",
                        condition_attribute="vaccine.cold_chain_requirements",
                        condition_stated="2-8C",
                    )
                )
            }
        )
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual(shelf.condition_stated, "2-8C")


class GridCompletenessTest(unittest.TestCase):
    def test_every_column_gets_a_row_however_the_reading_went(self) -> None:
        """Including the ones nothing was found for, and the ones that failed.

        A hole would read as "the document is silent" and mean "we never found out".
        """
        client = Client({"shelf_life": stated(one("24 months", "minimum 24 months"))})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        self.assertEqual(
            sorted({r.attribute for r in records}), sorted(COLUMNS)
        )
        Corpus(documents=(DOCUMENT,), records=tuple(records))

    def test_a_model_that_answers_nothing_produces_a_flagged_row(self) -> None:
        class Dead:
            def call_structured(self, *args, **kwargs):
                return None

        records, report = extract_document(DOCUMENT, BLOCKS, Dead())
        self.assertEqual({r.status for r in records}, {"uncertain"})
        self.assertEqual(report.unanswered, len(COLUMNS))
        Corpus(documents=(DOCUMENT,), records=tuple(records))

    def test_an_out_of_vocabulary_status_is_flagged_rather_than_trusted(self) -> None:
        """Reading a malformed answer as `stated` would promote a broken response."""
        client = Client(
            {
                "shelf_life": {
                    "status": "definitely",
                    "reason": "",
                    "values": [one("24 months", "minimum 24 months")],
                }
            }
        )
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        shelf = [r for r in records if r.attribute == "vaccine.shelf_life"][0]
        self.assertEqual(shelf.status, "uncertain")

    def test_silence_carries_the_reason_the_document_gave_for_it(self) -> None:
        records, report = extract_document(DOCUMENT, BLOCKS, Client({}))
        self.assertEqual(report.silent, len(COLUMNS))
        self.assertTrue(all(r.reason for r in records))


class ClassificationTest(unittest.TestCase):
    def test_only_filterable_columns_are_classified(self) -> None:
        """One call per filterable value, and none for a column that is read."""
        client = Client({"target_population": stated(
            one("infants aged 6-14 weeks", "infants aged 6-14 weeks")
        ), "shelf_life": stated(one("24 months", "minimum 24 months"))})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)

        class Tagger:
            def __init__(self):
                self.calls = 0

            def call_structured(self, *args, **kwargs):
                self.calls += 1
                return {"tags": ["infants"], "reason": "an age band"}

        tagger = Tagger()
        tagged, report = classify_records(records, "vaccine", tagger)
        self.assertEqual(tagger.calls, 1)
        by_attribute = {r.attribute: r for r in tagged}
        self.assertEqual(by_attribute["vaccine.target_population"].tags, ("infants",))
        self.assertEqual(by_attribute["vaccine.shelf_life"].tags, ())

    def test_a_tag_outside_the_vocabulary_is_dropped(self) -> None:
        client = Client({"target_population": stated(
            one("infants aged 6-14 weeks", "infants aged 6-14 weeks")
        )})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)

        class Tagger:
            def call_structured(self, *args, **kwargs):
                return {"tags": ["infants", "toddlers"], "reason": ""}

        tagged, _ = classify_records(records, "vaccine", Tagger())
        row = [r for r in tagged if r.attribute == "vaccine.target_population"][0]
        self.assertEqual(row.tags, ("infants",))

    def test_nothing_fitting_the_vocabulary_leaves_the_value_untagged(self) -> None:
        """Untagged and fully readable, rather than filed under the nearest tag.

        A value under the wrong tag makes a reader's filtered results silently wrong. An
        untagged one is still in the archive and still counted.
        """
        # Its own block, because the value has to survive verification before there is
        # anything to classify - and none of the shared blocks names an occupation.
        blocks = BLOCKS + [
            Block(
                "b5",
                "Target population: frontline health workers in outbreak settings.",
                "population",
                ["Clinical"],
            )
        ]
        client = Client({"target_population": stated(
            one(
                "frontline health workers",
                "Target population: frontline health workers in outbreak settings",
            )
        )})
        records, _ = extract_document(DOCUMENT, blocks, client)

        class Tagger:
            def call_structured(self, *args, **kwargs):
                return {"tags": [], "reason": "an occupation, not an age band"}

        tagged, report = classify_records(records, "vaccine", Tagger())
        row = [r for r in tagged if r.attribute == "vaccine.target_population"][0]
        self.assertEqual(row.tags, ())
        self.assertEqual(report.untagged, 1)

    def test_a_classifier_that_answers_nothing_leaves_the_row_intact(self) -> None:
        client = Client({"target_population": stated(
            one("infants aged 6-14 weeks", "infants aged 6-14 weeks")
        )})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)

        class Dead:
            def call_structured(self, *args, **kwargs):
                return None

        tagged, report = classify_records(records, "vaccine", Dead())
        row = [r for r in tagged if r.attribute == "vaccine.target_population"][0]
        self.assertEqual(row.stated, "infants aged 6-14 weeks")
        self.assertEqual(row.tags, ())
        self.assertEqual(report.untagged, 1)

    def test_the_classifier_reads_the_value_not_the_document(self) -> None:
        """Which is what makes a vocabulary change cheap to apply.

        Adding a tag means reclassifying a few dozen short strings, not re-reading fifty
        documents.
        """
        client = Client({"target_population": stated(
            one("infants aged 6-14 weeks", "infants aged 6-14 weeks")
        )})
        records, _ = extract_document(DOCUMENT, BLOCKS, client)
        seen = []

        class Tagger:
            def call_structured(self, system_prompt, user_message, *args, **kwargs):
                seen.append(user_message)
                return {"tags": ["infants"], "reason": ""}

        classify_records(records, "vaccine", Tagger())
        self.assertNotIn("Presentation:", seen[0])
        self.assertIn("infants aged 6-14 weeks", seen[0])


class PreparationTest(unittest.TestCase):
    def test_a_prepared_document_renders_its_text_once(self) -> None:
        """The unit of parallelism is (prepared document, column).

        One flat pool over every pair, rather than a pool over attributes inside a pool
        over documents - nested pools multiply into a concurrency nobody declared.
        """
        prepared = prepare_document(DOCUMENT, BLOCKS)
        self.assertEqual(len(prepared.columns()), len(COLUMNS))
        self.assertIn("Shelf life:", prepared.text)
        self.assertEqual(set(prepared.blocks_by_id), {"b1", "b2", "b3", "b4"})


if __name__ == "__main__":
    unittest.main()
