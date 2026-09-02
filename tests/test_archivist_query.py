"""Reading the corpus: what groups with what, what never merges, and what the route says.

The load-bearing test in this file is the one that proves an iTPP's values and a cTPP's
never land in the same list. An iTPP states a class-level ambition and a cTPP states one
candidate's commitment, so a number blending them describes neither product. The nesting
is what makes that unrepresentable rather than merely discouraged, and it holds even when
one of the two types has nothing to report.

The other is the partition: for every column, every matched document appears in exactly
one of stated, uncertain, or silent. That is what makes "three of nineteen specified this"
a count rather than an impression.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app
from services.archivist import (
    Corpus,
    CorpusDocument,
    CorpusRecord,
    CorpusQuery,
    TagFilter,
    available_filters,
    indexed_attributes,
    run_query,
)

COLUMNS = [column.attribute for column in indexed_attributes("vaccine")]
SHELF = "vaccine.shelf_life"
POPULATION = "vaccine.target_population"


def document(document_id: str, indication: str, source_type: str) -> CorpusDocument:
    return CorpusDocument(
        id=document_id,
        title=f"{indication} {source_type}",
        org="bmgf",
        intervention_class="vaccine",
        indication=indication,
        source_type=source_type,
    )


def grid(document_id: str, stated: dict, tags: dict | None = None):
    """A complete grid for one document: a value where given, silence everywhere else."""
    tags = tags or {}
    rows = []
    for attribute in COLUMNS:
        if attribute in stated:
            words, block = stated[attribute]
            rows.append(
                CorpusRecord(
                    document_id=document_id,
                    attribute=attribute,
                    status="stated",
                    stated=words,
                    quote=words,
                    block_text=block,
                    block_id="b1",
                    section_label="s",
                    tags=tags.get(attribute, ()),
                )
            )
        else:
            rows.append(
                CorpusRecord(
                    document_id=document_id,
                    attribute=attribute,
                    status="not_stated",
                    reason="not specified",
                )
            )
    return rows


DOCUMENTS = (
    document("mal-itpp", "malaria", "itpp"),
    document("mal-ctpp", "malaria", "ctpp"),
    document("tb-itpp", "tuberculosis", "itpp"),
    document("rsv-itpp", "rsv", "itpp"),
)

RECORDS = tuple(
    grid("mal-itpp", {SHELF: ("24 months", "shelf life 24 months"),
                      POPULATION: ("infants", "infants")}, {POPULATION: ("infants",)})
    + grid("mal-ctpp", {SHELF: ("36 months", "shelf life 36 months"),
                        POPULATION: ("infants", "infants")}, {POPULATION: ("infants",)})
    + grid("tb-itpp", {POPULATION: ("adolescents and adults", "adolescents and adults")},
           {POPULATION: ("adolescents", "adults")})
    + grid("rsv-itpp", {SHELF: ("24 months", "shelf life 24 months"),
                        POPULATION: ("pregnant women", "pregnant women")},
           {POPULATION: ("pregnant_women",)})
)

CORPUS = Corpus(documents=DOCUMENTS, records=RECORDS, built_at="2026-08-23T00:00:00+00:00")


class GroupingTest(unittest.TestCase):
    def test_document_types_are_never_merged(self) -> None:
        """The invariant this whole shape exists for."""
        answer = run_query(CORPUS, CorpusQuery(intervention_class="vaccine", attributes=(SHELF,)))
        groups = {group.source_type: group for group in answer.attributes[0].groups}
        self.assertEqual(sorted(groups), ["ctpp", "itpp"])
        self.assertEqual([r.stated for r in groups["ctpp"].values], ["36 months"])
        self.assertEqual(
            sorted(r.stated for r in groups["itpp"].values), ["24 months", "24 months"]
        )

    def test_a_document_type_with_only_silence_still_gets_a_heading(self) -> None:
        """"No cTPP in the archive specified this" is one of the two answers wanted."""
        answer = run_query(
            CORPUS,
            CorpusQuery(intervention_class="vaccine", attributes=("vaccine.thermostability",)),
        )
        groups = {group.source_type: group for group in answer.attributes[0].groups}
        self.assertEqual(sorted(groups), ["ctpp", "itpp"])
        self.assertEqual(groups["ctpp"].values, ())
        self.assertEqual(groups["ctpp"].silent, ("mal-ctpp",))

    def test_every_matched_document_lands_in_exactly_one_state_per_column(self) -> None:
        answer = run_query(CORPUS, CorpusQuery(intervention_class="vaccine"))
        expected = sorted(document.id for document in answer.documents)
        for group in answer.attributes:
            seen = []
            for source_group in group.groups:
                seen += [r.document_id for r in source_group.values]
                seen += [r.document_id for r in source_group.uncertain]
                seen += list(source_group.silent)
            with self.subTest(attribute=group.attribute):
                self.assertEqual(sorted(seen), expected)

    def test_counts_are_derived_from_the_lists_they_describe(self) -> None:
        """So a count cannot disagree with what is shown under it."""
        answer = run_query(CORPUS, CorpusQuery(intervention_class="vaccine", attributes=(SHELF,)))
        group = answer.attributes[0]
        self.assertEqual(group.documents_answering, 3)
        self.assertEqual(group.documents_total, 4)

    def test_the_silence_question_is_answerable(self) -> None:
        """Nothing in the archive specified thermostability, out of four profiles."""
        answer = run_query(
            CORPUS,
            CorpusQuery(intervention_class="vaccine", attributes=("vaccine.thermostability",)),
        )
        group = answer.attributes[0]
        self.assertEqual((group.documents_answering, group.documents_total), (0, 4))

    def test_source_type_order_is_stable(self) -> None:
        """Two runs over one corpus answer identically.

        Corpus order would do for documents, but a source type first appears wherever its
        first document happens to sit.
        """
        first = run_query(CORPUS, CorpusQuery(intervention_class="vaccine"))
        second = run_query(CORPUS, CorpusQuery(intervention_class="vaccine"))
        self.assertEqual(
            [g.source_type for g in first.attributes[0].groups],
            [g.source_type for g in second.attributes[0].groups],
        )


class FilterTest(unittest.TestCase):
    def test_a_tag_filter_selects_documents_not_rows(self) -> None:
        """Filtering for infants returns every column of the infant profiles.

        Not only their population row - a reader narrowing by population wants the shelf
        lives of the profiles written for infants.
        """
        answer = run_query(
            CORPUS,
            CorpusQuery(
                intervention_class="vaccine",
                attributes=(SHELF,),
                tags=(TagFilter(POPULATION, ("infants",)),),
            ),
        )
        self.assertEqual(
            sorted(document.id for document in answer.documents), ["mal-ctpp", "mal-itpp"]
        )
        groups = {group.source_type: group for group in answer.attributes[0].groups}
        self.assertEqual([r.stated for r in groups["itpp"].values], ["24 months"])

    def test_tags_within_one_filter_are_alternatives(self) -> None:
        answer = run_query(
            CORPUS,
            CorpusQuery(
                intervention_class="vaccine",
                attributes=(SHELF,),
                tags=(TagFilter(POPULATION, ("infants", "pregnant_women")),),
            ),
        )
        self.assertEqual(len(answer.documents), 3)

    def test_separate_filters_must_all_match(self) -> None:
        answer = run_query(
            CORPUS,
            CorpusQuery(
                intervention_class="vaccine",
                indications=("malaria",),
                source_types=("ctpp",),
            ),
        )
        self.assertEqual([document.id for document in answer.documents], ["mal-ctpp"])

    def test_no_attributes_means_every_column(self) -> None:
        answer = run_query(CORPUS, CorpusQuery(intervention_class="vaccine"))
        self.assertEqual([group.attribute for group in answer.attributes], COLUMNS)

    def test_columns_answer_in_declaration_order_whatever_order_was_asked(self) -> None:
        answer = run_query(
            CORPUS,
            CorpusQuery(intervention_class="vaccine", attributes=(SHELF, POPULATION)),
        )
        self.assertEqual(
            [group.attribute for group in answer.attributes], [POPULATION, SHELF]
        )

    def test_available_filters_describe_the_corpus_not_the_vocabulary(self) -> None:
        """Offering thirteen indications when the archive holds three returns nothing.

        A filter that produces an empty result and no explanation is worse than one that
        was never offered.
        """
        filters = available_filters(CORPUS, "vaccine")
        # Sorted, like the other two. First-appearance order would reshuffle the picker
        # every time a document was added.
        self.assertEqual(filters["indications"], ("malaria", "rsv", "tuberculosis"))
        self.assertEqual(filters["source_types"], ("ctpp", "itpp"))


class RefusalTest(unittest.TestCase):
    def test_an_attribute_that_is_not_a_column_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            CorpusQuery(intervention_class="vaccine", attributes=("vaccine.efficacy",))

    def test_a_tag_outside_the_vocabulary_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            CorpusQuery(
                intervention_class="vaccine", tags=(TagFilter(POPULATION, ("toddlers",)),)
            )

    def test_filtering_on_a_column_that_is_read_rather_than_filtered_says_so(self) -> None:
        with self.assertRaises(ValueError) as caught:
            CorpusQuery(intervention_class="vaccine", tags=(TagFilter(SHELF, ("x",)),))
        self.assertIn("read, not", str(caught.exception))

    def test_an_unindexed_class_is_refused(self) -> None:
        with self.assertRaises(LookupError):
            CorpusQuery(intervention_class="drug")


class RouteTest(unittest.TestCase):
    """The API over an empty archive, which is the state it ships in."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_the_route_s_default_class_is_one_that_has_columns(self) -> None:
        """Otherwise every default request is refused and nothing says why."""
        from api.routes.archivist import DEFAULT_INTERVENTION_CLASS
        from services.archivist import INDEXED_ATTRIBUTES

        self.assertIn(DEFAULT_INTERVENTION_CLASS, INDEXED_ATTRIBUTES)

    def test_the_corpus_route_publishes_the_columns_and_their_fences(self) -> None:
        payload = self.client.get("/api/archivist/corpus").json()
        self.assertEqual(
            [column["attribute"] for column in payload["columns"]], COLUMNS
        )
        shelf = next(c for c in payload["columns"] if c["attribute"] == SHELF)
        self.assertEqual(shelf["quantity"], "duration")
        self.assertIn("vaccine.thermostability", shelf["not_confused_with"])

    def test_a_filterable_column_publishes_its_vocabulary_and_others_do_not(self) -> None:
        """The presence of a vocabulary is the client's permission to offer a picker."""
        payload = self.client.get("/api/archivist/corpus").json()
        by_attribute = {c["attribute"]: c for c in payload["columns"]}
        self.assertTrue(by_attribute[POPULATION]["tags"])
        self.assertEqual(by_attribute[SHELF]["tags"], [])

    def test_an_empty_archive_is_a_state_rather_than_an_error(self) -> None:
        payload = self.client.get("/api/archivist/corpus").json()
        self.assertEqual(payload["documents"], [])
        self.assertEqual(payload["built_at"], "")

    def test_an_unindexed_class_is_refused_with_the_declared_list(self) -> None:
        response = self.client.get("/api/archivist/corpus?intervention_class=drug")
        self.assertEqual(response.status_code, 422)
        self.assertIn("vaccine", response.json()["detail"])

    def test_a_query_over_an_empty_archive_answers_every_column(self) -> None:
        payload = self.client.post(
            "/api/archivist/query", json={"intervention_class": "vaccine"}
        ).json()
        self.assertEqual(len(payload["attributes"]), len(COLUMNS))
        self.assertEqual(payload["documents"], [])

    def test_a_bad_filter_is_refused_with_the_reason(self) -> None:
        """Rather than returning nothing, which looks like an empty archive."""
        response = self.client.post(
            "/api/archivist/query",
            json={"intervention_class": "vaccine", "attributes": ["vaccine.efficacy"]},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("not corpus columns", response.json()["detail"])

    def test_the_route_offers_no_way_to_start_a_run(self) -> None:
        """Archivist reads a reviewed artifact. There is nothing to run and nothing to
        upload, and an endpoint implying otherwise would suggest the archive is built on
        demand."""
        # Read the published schema rather than walking `app.routes`. Starlette 1.0
        # stopped flattening included routers into that list, so the walk silently
        # finds nothing and an absence assertion passes for the wrong reason. The
        # OpenAPI document is the contract this test is actually about.
        paths = {
            path
            for path in app.openapi()["paths"]
            if path.startswith("/api/archivist")
        }
        self.assertEqual(paths, {"/api/archivist/corpus", "/api/archivist/query"})


if __name__ == "__main__":
    unittest.main()
