"""The whole tool, one seam at a time, from a manifest row to an HTTP response.

Every other Archivist test checks one layer. This one checks that they connect, because a
seam is exactly what unit tests cannot see: each side can be right about its own shape and
wrong about the other's. The chain here is the real one, with only the model replaced:

    manifest -> blocks -> extract -> classify -> Corpus -> write -> load -> query -> route

The documents are synthetic and so are the model's answers, but nothing else is stubbed.
The verification, the quantity parsing, the grid invariants, the JSON round trip, the
re-validation on load, and the grouping are all the production code paths.

The corpus deliberately contains an awkward set: two document types, a two-bound value, a
conditional value, a fabricated quote that must be discarded, an untaggable population, and
an attribute nobody specified. Each of those is a thing that could pass through one layer
and break at the next.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from services.archivist import Corpus, indexed_attributes, load_corpus, write_corpus
from services.archivist.manifest import load_manifest
from services.archivist.stages.classifier import classify_records
from services.archivist.stages.extractor import extract_attribute, prepare_document
import services.archivist.corpus_store as corpus_store

COLUMNS = [column.attribute for column in indexed_attributes("vaccine")]

MANIFEST = """
documents:
  - id: mal-itpp
    file: mal_itpp.docx
    title: Malaria Vaccine iTPP v3
    org: bmgf
    source_type: itpp
    intervention_class: vaccine
    indication: malaria
  - id: mal-ctpp
    file: mal_ctpp.docx
    title: Malaria Candidate cTPP
    org: bmgf
    source_type: ctpp
    intervention_class: vaccine
    indication: malaria
"""


@dataclass
class Block:
    id: str
    content: str
    section_label: str = ""
    heading_stack: list = field(default_factory=list)


BLOCKS = {
    "mal-itpp": [
        Block("b1", "Shelf life: minimum 24 months, optimal 36 months at 2-8C.",
              "stability", ["Product Characteristics"]),
        Block("b2", "Target population: infants aged 6-14 weeks.", "population",
              ["Clinical"]),
        Block("b3", "Delivered through routine EPI immunisation visits.", "delivery",
              ["Programmatic"]),
        Block("b4", "Price: $1.50 per dose for Gavi-eligible countries.", "pricing",
              ["Commercial"]),
    ],
    "mal-ctpp": [
        Block("c1", "Shelf life is 18 months for the liquid presentation.", "stability",
              ["Product Characteristics"]),
        Block("c2", "Intended for frontline health workers in outbreak response.",
              "population", ["Clinical"]),
    ],
}

#: What the model returns, per document and attribute. Everything absent is silence, which
#: is the common case in a real profile.
ANSWERS: dict[tuple[str, str], dict] = {
    ("mal-itpp", "shelf_life"): {
        "status": "stated",
        "reason": "",
        "values": [
            {"bound": "minimum", "stated": "24 months", "quote": "minimum 24 months",
             "condition_attribute": "", "condition_stated": ""},
            {"bound": "optimal", "stated": "36 months", "quote": "optimal 36 months",
             "condition_attribute": "", "condition_stated": ""},
        ],
    },
    ("mal-itpp", "target_population"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "infants aged 6-14 weeks",
                    "quote": "Target population: infants aged 6-14 weeks",
                    "condition_attribute": "", "condition_stated": ""}],
    },
    ("mal-itpp", "delivery_strategy"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "routine EPI immunisation visits",
                    "quote": "Delivered through routine EPI immunisation visits",
                    "condition_attribute": "", "condition_stated": ""}],
    },
    ("mal-itpp", "procurement_price"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "$1.50 per dose",
                    "quote": "Price: $1.50 per dose for Gavi-eligible countries",
                    "condition_attribute": "vaccine.target_countries",
                    "condition_stated": "Gavi-eligible countries"}],
    },
    # A fabricated quote: nothing in the document says this, so it must not become a value.
    ("mal-itpp", "thermostability"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "CTC-eligible",
                    "quote": "the vaccine is CTC-eligible",
                    "condition_attribute": "", "condition_stated": ""}],
    },
    ("mal-ctpp", "shelf_life"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "18 months",
                    "quote": "Shelf life is 18 months for the liquid presentation",
                    "condition_attribute": "vaccine.presentation",
                    "condition_stated": "liquid presentation"}],
    },
    # A real population that no tag in the vocabulary covers.
    ("mal-ctpp", "target_population"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "frontline health workers",
                    "quote": "Intended for frontline health workers in outbreak response",
                    "condition_attribute": "", "condition_stated": ""}],
    },
    ("mal-ctpp", "delivery_strategy"): {
        "status": "stated", "reason": "",
        "values": [{"bound": "single", "stated": "outbreak response",
                    "quote": "frontline health workers in outbreak response",
                    "condition_attribute": "", "condition_stated": ""}],
    },
}

SILENT = {"status": "not_stated", "reason": "not specified in this profile", "values": []}

TAGS = {
    "infants aged 6-14 weeks": ["infants"],
    "routine EPI immunisation visits": ["routine_immunization"],
    "outbreak response": ["outbreak_response"],
    # Nothing fits: an occupation is not an age band, and the classifier is allowed to
    # say so rather than reaching for the nearest tag.
    "frontline health workers": [],
}


class Model:
    """Stands in for the provider on both stages, keyed by what it was asked."""

    def __init__(self):
        self.extraction_calls = 0
        self.classification_calls = 0

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        if user_message.startswith("value: "):
            self.classification_calls += 1
            value = user_message.split("value: ", 1)[1].split("\n", 1)[0]
            return {"tags": TAGS.get(value, []), "reason": ""}
        self.extraction_calls += 1
        attribute = user_message.rsplit("Read `", 1)[1].split("`")[0]
        document_id = self._document_of(user_message)
        return ANSWERS.get((document_id, attribute), SILENT)

    @staticmethod
    def _document_of(user_message: str) -> str:
        return "mal-itpp" if "[b1]" in user_message else "mal-ctpp"


def build() -> tuple[Corpus, Model]:
    """Run the real chain over synthetic input, exactly as the build script does."""
    manifest = Path(tempfile.mkdtemp()) / "manifest.yaml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    entries = load_manifest(manifest)
    model = Model()

    # Phase two: one flat pool over every (document, attribute) pair. Run in sequence here
    # so the test is deterministic; the pairs are independent either way.
    records = []
    for entry in entries:
        prepared = prepare_document(entry.document(), BLOCKS[entry.id])
        for column in prepared.columns():
            column_records, _ = extract_attribute(prepared, column, model)
            records.extend(column_records)

    # Phase three: tag the filterable values.
    records, _ = classify_records(records, "vaccine", model)

    return (
        Corpus(
            documents=tuple(entry.document() for entry in entries),
            records=tuple(records),
            built_at="2026-08-23T00:00:00+00:00",
        ),
        model,
    )


class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus, cls.model = build()
        cls.path = Path(tempfile.mkdtemp()) / "corpus.json"
        write_corpus(cls.corpus, cls.path)
        # The route resolves the path at call time, so pointing the module constant at the
        # temporary artifact exercises the real loader rather than replacing it.
        cls._original = corpus_store.CORPUS_FILE
        corpus_store.CORPUS_FILE = cls.path
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        corpus_store.CORPUS_FILE = cls._original

    def test_the_build_made_one_call_per_document_and_attribute(self) -> None:
        self.assertEqual(self.model.extraction_calls, 2 * len(COLUMNS))

    def test_the_classifier_ran_only_on_filterable_values(self) -> None:
        """Four: two populations and two delivery strategies. Not the shelf lives."""
        self.assertEqual(self.model.classification_calls, 4)

    def test_the_grid_is_complete_for_both_documents(self) -> None:
        for document in self.corpus.documents:
            for attribute in COLUMNS:
                with self.subTest(document=document.id, attribute=attribute):
                    self.assertTrue(
                        any(
                            record.document_id == document.id
                            and record.attribute == attribute
                            for record in self.corpus.records
                        )
                    )

    def test_the_fabricated_quote_never_became_a_value(self) -> None:
        """It survived neither extraction nor the round trip.

        The row is still there, flagged - the grid has no holes - and the other profile,
        which said nothing about this attribute, is silent rather than flagged. The two
        states are distinguishable, which is the whole reason `uncertain` exists.
        """
        rows = {
            record.document_id: record
            for record in load_corpus(self.path).records
            if record.attribute == "vaccine.thermostability"
        }
        self.assertEqual(rows["mal-itpp"].status, "uncertain")
        self.assertEqual(rows["mal-itpp"].stated, "")
        self.assertEqual(rows["mal-ctpp"].status, "not_stated")

    def test_a_written_corpus_reloads_and_revalidates(self) -> None:
        reloaded = load_corpus(self.path)
        self.assertEqual(len(reloaded.records), len(self.corpus.records))
        self.assertEqual(len(reloaded.documents), 2)

    def test_quantities_survive_the_round_trip(self) -> None:
        by_key = {
            (r.document_id, r.attribute, r.bound): r for r in load_corpus(self.path).records
        }
        self.assertEqual(
            (by_key[("mal-itpp", "vaccine.shelf_life", "minimum")].magnitude, "months"),
            (24.0, by_key[("mal-itpp", "vaccine.shelf_life", "minimum")].unit),
        )
        self.assertEqual(
            by_key[("mal-itpp", "vaccine.procurement_price", "single")].magnitude, 1.5
        )
        self.assertEqual(
            by_key[("mal-itpp", "vaccine.procurement_price", "single")].unit, "usd"
        )

    def test_the_conditional_value_kept_both_halves_of_its_condition(self) -> None:
        row = next(
            r
            for r in load_corpus(self.path).records
            if r.document_id == "mal-ctpp" and r.attribute == "vaccine.shelf_life"
        )
        self.assertEqual(row.condition_attribute, "vaccine.presentation")
        self.assertEqual(row.condition_stated, "liquid presentation")

    def test_an_untaggable_population_is_kept_and_left_untagged(self) -> None:
        row = next(
            r
            for r in load_corpus(self.path).records
            if r.document_id == "mal-ctpp" and r.attribute == "vaccine.target_population"
        )
        self.assertEqual(row.stated, "frontline health workers")
        self.assertEqual(row.tags, ())

    def test_the_route_publishes_what_the_archive_holds(self) -> None:
        payload = self.client.get("/api/archivist/corpus").json()
        self.assertEqual(len(payload["documents"]), 2)
        self.assertEqual(payload["source_types"], ["ctpp", "itpp"])
        self.assertEqual(payload["indications"], ["malaria"])
        self.assertTrue(payload["built_at"])

    def test_the_route_keeps_the_two_document_types_apart(self) -> None:
        """The end-to-end form of the invariant this tool is built around."""
        payload = self.client.post(
            "/api/archivist/query",
            json={"intervention_class": "vaccine", "attributes": ["vaccine.shelf_life"]},
        ).json()
        groups = {g["source_type"]: g for g in payload["attributes"][0]["groups"]}
        self.assertEqual(sorted(groups), ["ctpp", "itpp"])
        self.assertEqual([v["stated"] for v in groups["ctpp"]["values"]], ["18 months"])
        self.assertEqual(
            sorted(v["stated"] for v in groups["itpp"]["values"]),
            ["24 months", "36 months"],
        )

    def test_the_route_answers_the_silence_question(self) -> None:
        payload = self.client.post(
            "/api/archivist/query",
            json={"intervention_class": "vaccine", "attributes": ["vaccine.dosing_schedule"]},
        ).json()
        groups = payload["attributes"][0]["groups"]
        self.assertEqual(
            sorted(id for group in groups for id in group["silent"]),
            ["mal-ctpp", "mal-itpp"],
        )

    def test_a_tag_filter_selects_the_right_profile_through_the_route(self) -> None:
        """And returns a column the tag was not on, which is the point of the filter."""
        payload = self.client.post(
            "/api/archivist/query",
            json={
                "intervention_class": "vaccine",
                "attributes": ["vaccine.shelf_life"],
                "tags": [
                    {
                        "attribute": "vaccine.delivery_strategy",
                        "values": ["outbreak_response"],
                    }
                ],
            },
        ).json()
        self.assertEqual([d["id"] for d in payload["documents"]], ["mal-ctpp"])
        values = [
            value
            for group in payload["attributes"][0]["groups"]
            for value in group["values"]
        ]
        self.assertEqual([value["stated"] for value in values], ["18 months"])

    def test_every_value_the_route_returns_carries_a_checkable_quote(self) -> None:
        """The guarantee a reader relies on, asserted at the outermost layer."""
        payload = self.client.post(
            "/api/archivist/query", json={"intervention_class": "vaccine"}
        ).json()
        checked = 0
        for group in payload["attributes"]:
            for source_group in group["groups"]:
                for value in source_group["values"]:
                    with self.subTest(attribute=group["attribute"]):
                        self.assertIn(value["quote"], value["block_text"])
                        self.assertIn(value["stated"], value["quote"])
                        self.assertTrue(value["block_id"])
                    checked += 1
        # Five from the iTPP - a shelf life at two bounds, a population, a delivery
        # strategy and a price - and three from the cTPP.
        self.assertEqual(checked, 8, "the corpus under test lost or gained a value")


if __name__ == "__main__":
    unittest.main()
