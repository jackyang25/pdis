"""Every lane declares what it owns, and every declaration is checked against the code.

The map exists because the lane set had become a taxonomy by accident: three lanes
covered molecular reference data, one covered regulatory, and the institutions the
configs name as priorities had none at all. Nobody chose that shape - it emerged one
adapter at a time, and no surface stated it, so no one could see it.

A declaration nobody checks is worse than none, because it reads as a decision. So the
tests below fall into two halves:

    the map is complete   every lane declares class, jurisdiction, and what it feeds
    the map is true       what a lane declares matches what its adapter actually does

The second half is the one that matters. UniProt declared nothing and reached nothing:
its findings were `reference`, so insight extraction filtered them out, and it built no
records, so no projection saw them. It was registered, enabled in seven configs, and
consumed a request per run to tell a reader nothing. `feeds` makes that impossible to
declare, and `test_a_lane_feeding_insights_returns_evidence` makes it impossible to
mis-declare.

Gaps are asserted as declared gaps rather than tolerated silently: `MISSING_COVERAGE`
below names the classes with no lane, so closing one is deleting a line here.
"""

from __future__ import annotations

import pathlib
import unittest
import xml.etree.ElementTree as ElementTree
from unittest.mock import patch

from datetime import datetime, timezone

from services.scout.pipeline import (
    _finding_batches,
    _interleave_by_evidence_class,
)
import services.searcher.stages.pubmed as pubmed_stage
from services.scout.models import (
    QUERY_TRACK_BUDGET,
    RUN_SCOPE_DIMENSIONS,
    Attribute,
    QueryIntent,
    RetrievalScopeLedger,
    load_config,
)
from services.scout.stages.intent_builder import build_retrieval_intents
from services.searcher import (
    Finding,
    RetrievalIntent,
    SourceQueryIntent,
    plan_requests,
    source_specs,
)
from shared.vocabulary import (
    DOWNSTREAM_OUTPUTS,
    EVIDENCE_CLASSES,
    JURISDICTIONS,
    SCOPE_DIMENSIONS,
)

SOURCES_DIR = pathlib.Path(__file__).resolve().parent.parent / "services" / "searcher" / "sources"
CONFIG_DIR = pathlib.Path(__file__).resolve().parent.parent / "services" / "scout" / "configs"

# ---------------------------------------------------------------------------
# Declared gaps
#
# Every hole in the pipeline, named, in the order a value travels: what nothing
# supplies, what no lane can act on, what class of evidence has no lane at all, and
# what is wired for one lane but not its siblings.
#
# They are here rather than in prose because a hole nobody enumerates is a hole a
# reader discovers by getting no answer. Each list has two tests: one that its entries
# are still holes, and one that it names nothing that has stopped being a hole. The
# second matters more - a gap list that outlives its gap understates coverage, and a
# gap list naming something that no longer exists is maintenance for nothing.
# ---------------------------------------------------------------------------

#: Run scope dimensions nothing fills.
#:
#: Empty, and that is the assertion. `condition` and `intervention` come from the run
#: header; `region` comes from whichever attribute declares `supplies_scope: region`,
#: normalised by `scope_resolver` into a phrase a provider's location field can index.
#: A document that states only a policy tier such as "LMIC" still leaves region unset,
#: which is a supplier answering rather than a supplier missing.
MISSING_SCOPE_SUPPLIERS: dict[str, str] = {}

#: Scope dimensions no lane can act on.
#:
#: Empty, and that is the assertion: every dimension a caller can state reaches at least
#: one lane. It held `setting` until `setting` was removed from the vocabulary outright -
#: a dimension nothing supplied and nothing consumed was a placeholder kept alive by two
#: gap entries, not a dimension.
MISSING_SCOPE_CONSUMERS: dict[str, str] = {}

#: Evidence classes with no lane.
#:
#: Both are classes the Scout configs already name as priority institutions, which is
#: how the imbalance was found: the query layer was generating requests for a world the
#: lane layer could not reach, and they arrived as web prose whose excerpts cannot
#: support a quantitative claim.
MISSING_COVERAGE = {
    "access": "no procurement or financing body is reachable: the ToolUniverse catalogue exposes no Gavi, Global Fund or UNICEF Supply tool",
    "news": "reached by the web lane's program query set rather than a lane of its own, since no news provider is exposed",
}

#: Jurisdictions with no lane in any class.
#:
#: `lmic` is the one that matters, and it is the gap the geographic query track was
#: written for: SAHPRA, NMPA, CDSCO, BPOM and ANVISA are named priority institutions,
#: and WHO ICTRP is the one source that would aggregate the registries behind them.
MISSING_JURISDICTIONS = {
    "lmic": "no LMIC-specific provider is reachable: the catalogue exposes no WHO ICTRP, CTRI, ChiCTR, ReBEC or PACTR tool, and no national regulator outside the US. WHO Guidelines covers the normative half at global scope",
}

#: Registries that cannot narrow by `region`, and why not.
#:
#: ClinicalTrials.gov uses `query.locn` and ISRCTN compiles `country` to
#: `recruitmentCountry`, so both take a place name. CTIS is different in kind rather than
#: unfinished: its `country` parameter takes Member State Concerned codes, so the only
#: geographies it can be asked about are EU member states. A programme's region is
#: usually not one, and passing a name where a code is expected would return a full
#: result set while looking like a filter.
REGION_UNWIRED_REGISTRIES = {
    "ctis": "its country filter takes EU Member State codes, so a programme's region is not expressible",
}


def _adapter_source(key: str) -> str:
    return (SOURCES_DIR / f"{key}.py").read_text()


class DeclaredGapTests(unittest.TestCase):
    """Every gap list names real things, and only things that are still gaps.

    The staleness half is the one that earns its keep. A list outliving its gap
    understates coverage; a list naming something that no longer exists is maintenance
    for nothing, and it hid a real slip - `setting` sat in two gap lists after being
    removed from the vocabulary, and every other test still passed.
    """

    def test_scope_gaps_name_real_dimensions(self) -> None:
        for name, gaps in (
            ("MISSING_SCOPE_SUPPLIERS", MISSING_SCOPE_SUPPLIERS),
            ("MISSING_SCOPE_CONSUMERS", MISSING_SCOPE_CONSUMERS),
        ):
            with self.subTest(list=name):
                self.assertEqual(sorted(set(gaps) - SCOPE_DIMENSIONS), [])

    def test_a_scope_supplier_gap_names_a_run_scope_dimension(self) -> None:
        """A per-query dimension has no run-level supplier to be missing."""
        self.assertEqual(
            sorted(set(MISSING_SCOPE_SUPPLIERS) - set(RUN_SCOPE_DIMENSIONS)), []
        )

    def test_coverage_gaps_name_real_classes_and_jurisdictions(self) -> None:
        self.assertEqual(sorted(set(MISSING_COVERAGE) - EVIDENCE_CLASSES), [])
        self.assertEqual(sorted(set(MISSING_JURISDICTIONS) - JURISDICTIONS), [])

    def test_partial_wiring_names_registered_lanes(self) -> None:
        registered = {spec.key for spec in source_specs()}
        self.assertEqual(sorted(set(REGION_UNWIRED_REGISTRIES) - registered), [])

    def test_every_gap_carries_a_reason(self) -> None:
        for gaps in (
            MISSING_SCOPE_SUPPLIERS,
            MISSING_SCOPE_CONSUMERS,
            MISSING_COVERAGE,
            MISSING_JURISDICTIONS,
            REGION_UNWIRED_REGISTRIES,
        ):
            for key, reason in gaps.items():
                with self.subTest(gap=key):
                    self.assertGreater(len(reason.split()), 4, key)


class MapCompleteTests(unittest.TestCase):
    def test_every_lane_declares_its_place(self) -> None:
        for spec in source_specs():
            with self.subTest(lane=spec.key):
                self.assertIn(spec.evidence_class, EVIDENCE_CLASSES)
                self.assertIn(spec.jurisdiction, JURISDICTIONS)
                self.assertTrue(spec.feeds)
                self.assertLessEqual(set(spec.feeds), DOWNSTREAM_OUTPUTS)

    def test_every_class_is_either_covered_or_a_declared_gap(self) -> None:
        covered = {spec.evidence_class for spec in source_specs()}
        unaccounted = sorted(EVIDENCE_CLASSES - covered - set(MISSING_COVERAGE))
        self.assertEqual(
            unaccounted,
            [],
            f"evidence classes with neither a lane nor a declared gap: {unaccounted}",
        )

    def test_a_closed_gap_is_removed_from_the_list(self) -> None:
        """So the gap list cannot outlive the gap and understate coverage."""
        covered = {spec.evidence_class for spec in source_specs()}
        stale = sorted(covered & set(MISSING_COVERAGE))
        self.assertEqual(stale, [], f"declared gaps that now have a lane: {stale}")

    def test_declared_missing_jurisdictions_are_still_missing(self) -> None:
        covered = {spec.jurisdiction for spec in source_specs()}
        self.assertEqual(sorted(covered & set(MISSING_JURISDICTIONS)), [])

    def test_every_scope_dimension_is_read_or_a_declared_gap(self) -> None:
        """Both ends of the wire, checked the same way.

        `feeds` catches a lane whose output nothing reads. This catches the mirror
        image: a dimension the caller can state that no lane can act on. Region was
        exactly that - stated by the document, emphasised in a prompt, and unable to
        reach a single provider field.
        """
        read = {dimension for spec in source_specs() for dimension in spec.reads}
        unaccounted = sorted(
            SCOPE_DIMENSIONS - read - set(MISSING_SCOPE_CONSUMERS)
        )
        self.assertEqual(
            unaccounted,
            [],
            f"scope dimensions no lane reads and no gap declares: {unaccounted}",
        )

    def test_a_dimension_that_gained_a_consumer_leaves_the_gap_list(self) -> None:
        read = {dimension for spec in source_specs() for dimension in spec.reads}
        stale = sorted(read & set(MISSING_SCOPE_CONSUMERS))
        self.assertEqual(stale, [], f"declared gaps now read by a lane: {stale}")

    def test_a_registry_either_reads_region_or_says_why_not(self) -> None:
        """So a half-wired dimension stays visible instead of looking finished."""
        for spec in source_specs():
            if spec.evidence_class != "registry":
                continue
            with self.subTest(lane=spec.key):
                self.assertTrue(
                    "region" in spec.reads or spec.key in REGION_UNWIRED_REGISTRIES,
                    f"{spec.key}: registry that neither reads region nor declares why",
                )

    def test_every_downstream_output_has_at_least_one_lane(self) -> None:
        """A consumer with no producer is a feature that silently never runs."""
        produced = {output for spec in source_specs() for output in spec.feeds}
        self.assertEqual(sorted(DOWNSTREAM_OUTPUTS - produced), [])


class MapIsTrueTests(unittest.TestCase):
    """What a lane declares has to match what its adapter does."""

    def test_a_lane_feeding_insights_returns_evidence(self) -> None:
        """Insight extraction reads evidence-role findings only, so `reference` cannot.

        This is the UniProt check. A lane whose every finding is `reference` and which
        claims `insights` is claiming to reach a stage that filters it out.
        """
        for spec in source_specs():
            if "insights" not in spec.feeds:
                continue
            source = _adapter_source(spec.key)
            emits_reference = 'evidence_role="reference"' in source
            emits_evidence = 'evidence_role="evidence"' in source
            with self.subTest(lane=spec.key):
                self.assertFalse(
                    emits_reference and not emits_evidence,
                    f"{spec.key} declares `insights` but marks every finding "
                    "`reference`, which insight extraction filters out.",
                )

    def test_a_lane_feeding_landscape_builds_development_records(self) -> None:
        for spec in source_specs():
            if "landscape" not in spec.feeds:
                continue
            with self.subTest(lane=spec.key):
                self.assertIn(
                    "development_records=",
                    _adapter_source(spec.key) + _stage_source(spec.key),
                    f"{spec.key} declares `landscape` but builds no development record",
                )

    def test_a_lane_feeding_safety_builds_safety_observations(self) -> None:
        for spec in source_specs():
            if "safety" not in spec.feeds:
                continue
            with self.subTest(lane=spec.key):
                self.assertIn(
                    "safety_observations=",
                    _adapter_source(spec.key) + _stage_source(spec.key),
                    f"{spec.key} declares `safety` but builds no safety observation",
                )

    def test_a_lane_declaring_a_date_bound_passes_it_to_the_provider(self) -> None:
        """The declaration is a promise about the request, not about the result.

        A lane claiming to bound at the provider while filtering afterwards is the
        expensive failure: the request is spent on records that were never eligible,
        and the reader sees a window that only removed the answer, not the question.
        """
        for spec in source_specs():
            if not spec.honors_date_bound:
                continue
            with self.subTest(lane=spec.key):
                self.assertIn(
                    "published_since",
                    _adapter_source(spec.key),
                    f"{spec.key} declares honors_date_bound but never reads the bound",
                )

    def test_a_lane_not_declaring_a_date_bound_does_not_quietly_use_one(self) -> None:
        for spec in source_specs():
            if spec.honors_date_bound:
                continue
            with self.subTest(lane=spec.key):
                self.assertNotIn("published_since", _adapter_source(spec.key))

    def test_a_lane_reading_subjects_touches_the_entities_it_claims(self) -> None:
        """`subject` is the one dimension with a single unambiguous marker in code."""
        for spec in source_specs():
            source = _lane_source(spec.key)
            with self.subTest(lane=spec.key):
                self.assertEqual(
                    "subject" in spec.reads,
                    "intent.entities" in source,
                    f"{spec.key}: reads subject={'subject' in spec.reads} but "
                    f"intent.entities present={'intent.entities' in source}",
                )

    def test_a_lane_reading_a_condition_addresses_it(self) -> None:
        for spec in source_specs():
            if "condition" not in spec.reads:
                continue
            source = _lane_source(spec.key)
            with self.subTest(lane=spec.key):
                self.assertTrue(
                    "intent.indication" in source or '"condition"' in source,
                    f"{spec.key} declares it reads a condition but never uses one",
                )

    def test_a_lane_reading_no_condition_does_not_use_one(self) -> None:
        for spec in source_specs():
            if "condition" in spec.reads or spec.key == "web":
                continue
            with self.subTest(lane=spec.key):
                self.assertNotIn("intent.indication", _adapter_source(spec.key))

    def test_an_entity_addressed_lane_declares_the_types_it_reads(self) -> None:
        """A lane naming a subject in its request must say which subjects it accepts."""
        for spec in source_specs():
            source = _adapter_source(spec.key)
            reads_entities = "intent.entities" in source
            with self.subTest(lane=spec.key):
                self.assertEqual(
                    reads_entities,
                    bool(spec.required_entity_types),
                    f"{spec.key}: reads entities={reads_entities} but declares "
                    f"required_entity_types={list(spec.required_entity_types)}",
                )


class BatchCompositionTests(unittest.TestCase):
    """The map is read where it changes an answer, not only where it is displayed."""

    @staticmethod
    def _finding(source: str, ordinal: int) -> Finding:
        return Finding(
            url=f"https://example.org/{source}/{ordinal}",
            title=f"{source}-{ordinal}",
            query="q",
            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source=source,
        )

    def test_classes_alternate_so_one_prompt_holds_more_than_one_kind(self) -> None:
        """Retrieval returns lane by lane, so arrival order batches one class per prompt.

        A registry record and the literature it should be read against then never appear
        together, and a comparison the model cannot see in one prompt is one it cannot
        make.
        """
        arrival = (
            [self._finding("pubmed", i) for i in range(3)]
            + [self._finding("clinicaltrials", i) for i in range(2)]
            + [self._finding("fda", 0)]
        )
        mixed = [finding.title for finding in _interleave_by_evidence_class(arrival)]
        self.assertEqual(
            mixed,
            [
                "pubmed-0",
                "clinicaltrials-0",
                "fda-0",
                "pubmed-1",
                "clinicaltrials-1",
                "pubmed-2",
            ],
        )

    def test_each_lane_keeps_its_own_ranking(self) -> None:
        """Alternating must not reorder within a class, or a lane's relevance is lost."""
        arrival = [self._finding("pubmed", i) for i in range(3)] + [
            self._finding("ctis", i) for i in range(3)
        ]
        mixed = _interleave_by_evidence_class(arrival)
        for source in ("pubmed", "ctis"):
            self.assertEqual(
                [f.title for f in mixed if f.source == source],
                [f.title for f in arrival if f.source == source],
            )

    def test_nothing_is_dropped_or_duplicated(self) -> None:
        arrival = [self._finding("pubmed", i) for i in range(5)] + [
            self._finding("chembl", i) for i in range(2)
        ]
        mixed = _interleave_by_evidence_class(arrival)
        self.assertEqual(len(mixed), len(arrival))
        self.assertEqual({f.url for f in mixed}, {f.url for f in arrival})

    def test_the_batcher_actually_uses_the_interleaving(self) -> None:
        """Through `_finding_batches`, not the helper alone.

        Testing the helper only proves the helper works. Deleting its call from the
        batcher left every test above passing, which is the whole failure this covers:
        a correct function nothing invokes.
        """
        arrival = (
            [self._finding("pubmed", i) for i in range(3)]
            + [self._finding("clinicaltrials", i) for i in range(2)]
        )
        (batch,) = _finding_batches(arrival)
        self.assertEqual(
            [finding.title for finding in batch],
            [
                "pubmed-0",
                "clinicaltrials-0",
                "pubmed-1",
                "clinicaltrials-1",
                "pubmed-2",
            ],
        )

    def test_a_single_class_is_left_exactly_as_it_arrived(self) -> None:
        arrival = [self._finding("pubmed", i) for i in range(3)]
        self.assertEqual(_interleave_by_evidence_class(arrival), arrival)


class ScopeLedgerTests(unittest.TestCase):
    """What a run supplies, checked against what the lanes can use.

    `reads` says what a lane can be told. The ledger says what a run says. This closes
    the loop: a dimension supplied but unreadable is a value nothing acts on, and a
    dimension readable but unsupplied is a lane waiting on nobody. Region was the second
    kind and stayed invisible because neither end was written down.
    """

    def _ledger(self) -> RetrievalScopeLedger:
        """A fully supplied run: two header fields and a document-derived region."""
        return RetrievalScopeLedger.of(
            condition=("malaria", "header"),
            intervention=("vaccine", "header"),
            region=("Kenya", "document", ("profile/b-0007",)),
        )

    def test_the_ledger_covers_every_run_scope_dimension(self) -> None:
        """Including the unsupplied ones, or a hole reads as an omission."""
        stated = {entry.dimension for entry in self._ledger().entries}
        self.assertEqual(stated, set(RUN_SCOPE_DIMENSIONS))

    def test_run_scope_is_a_subset_of_the_declared_vocabulary(self) -> None:
        self.assertLessEqual(set(RUN_SCOPE_DIMENSIONS), SCOPE_DIMENSIONS)

    def test_every_supplied_dimension_reaches_at_least_one_lane(self) -> None:
        read = {dimension for spec in source_specs() for dimension in spec.reads}
        supplied = set(self._ledger().supplied())
        self.assertEqual(
            sorted(supplied - read),
            [],
            "a run states these and no lane can act on them: "
            f"{sorted(supplied - read)}",
        )

    def test_every_unsupplied_dimension_is_a_declared_gap(self) -> None:
        ledger = self._ledger()
        unsupplied = {
            entry.dimension for entry in ledger.entries if entry.provenance == "unset"
        }
        unaccounted = sorted(unsupplied - set(MISSING_SCOPE_SUPPLIERS))
        self.assertEqual(
            unaccounted,
            [],
            f"run scope dimensions nothing fills and no gap declares: {unaccounted}",
        )

    def test_a_dimension_that_gained_a_supplier_leaves_the_gap_list(self) -> None:
        supplied = set(self._ledger().supplied())
        stale = sorted(supplied & set(MISSING_SCOPE_SUPPLIERS))
        self.assertEqual(stale, [], f"declared gaps now supplied: {stale}")

    def test_a_document_value_must_cite_its_blocks(self) -> None:
        """Same bar as the numeric ledger: an untraceable reading is not a reading."""
        with self.assertRaises(ValueError):
            RetrievalScopeLedger.of(region=("sub-Saharan Africa", "document"))
        traced = RetrievalScopeLedger.of(
            region=("sub-Saharan Africa", "document", ("profile/b-0012",))
        )
        self.assertEqual(traced.entry("region").block_ids, ("profile/b-0012",))

    def test_a_value_and_its_provenance_cannot_disagree(self) -> None:
        with self.subTest("supplier with no value"):
            with self.assertRaises(ValueError):
                RetrievalScopeLedger.of(condition=("", "header"))
        with self.subTest("value with no supplier"):
            with self.assertRaises(ValueError):
                RetrievalScopeLedger.of(condition=("malaria", "unset"))

    def test_the_ledger_reaches_the_intents_it_scopes(self) -> None:
        """The wire itself: a ledger value has to arrive on every intent built from it."""
        attribute = Attribute(
            name="vaccine.efficacy",
            description="Efficacy against infection.",
            evidence_domain="clinical",
        )
        ledger = RetrievalScopeLedger.of(
            condition=("malaria", "header"),
            intervention=("vaccine", "header"),
            region=("Kenya", "document", ("profile/b-0001",)),
        )
        (intent,) = build_retrieval_intents(
            {"vaccine.efficacy": [QueryIntent(text="efficacy", tracks=["general"])]},
            [attribute],
            scope=ledger,
        )
        for dimension in ("condition", "intervention", "region"):
            self.assertEqual(intent.scope(dimension), ledger.value(dimension))


class NarrowingIsAdditiveTests(unittest.TestCase):
    """A narrowing adds a request beside the broad one; it never replaces it.

    The rule is already stated in `facet_groups`: "a precise request that names a
    product the source files differently returns nothing, and losing coverage is worse
    than lacking precision". It applies identically to a run-scope narrowing such as
    region. A programme aimed at one geography still has to be judged against trials run
    elsewhere, so restricting every request to its own region would silently answer a
    narrower question than the caller asked.

    Held here rather than in the adapter's own tests because it is the standard every
    narrowing dimension must meet, not a fact about ClinicalTrials.gov.
    """

    @staticmethod
    def _intent(**kwargs) -> RetrievalIntent:
        return RetrievalIntent(
            scope_ref="q",
            topic="melanoma",
            description="",
            indication="melanoma",
            intervention_class="vaccine",
            queries=(SourceQueryIntent(text="melanoma survival", tracks=("general",)),),
            **kwargs,
        )

    def test_a_stated_region_adds_a_request_rather_than_replacing_one(self) -> None:
        broad = plan_requests([self._intent()], sources=("clinicaltrials",))
        both = plan_requests(
            [self._intent(region="Kenya")], sources=("clinicaltrials",)
        )
        self.assertEqual(len(broad), 1)
        self.assertEqual(len(both), 2)
        # The unscoped request survives unchanged, byte for byte.
        self.assertEqual(both[0].query, broad[0].query)
        self.assertEqual(dict(both[0].options)["region"], "")

    def test_the_narrowed_request_carries_the_region(self) -> None:
        (_, narrowed) = plan_requests(
            [self._intent(region="Kenya")], sources=("clinicaltrials",)
        )
        self.assertEqual(dict(narrowed.options)["region"], "Kenya")
        # Distinguishable in the lane report, or two rows read as one request twice.
        self.assertIn("location:Kenya", narrowed.query)

    def test_no_region_means_no_extra_request(self) -> None:
        self.assertEqual(
            len(plan_requests([self._intent()], sources=("clinicaltrials",))), 1
        )


class DateBoundTests(unittest.TestCase):
    """The bound reaches the provider as a parameter, never as a query term."""

    def _esearch_parameters(self, **kwargs) -> dict[str, str]:
        captured: dict[str, dict[str, str]] = {}

        def fake_request_xml(endpoint, parameters, *, api_key=None):
            captured[endpoint] = dict(parameters)
            return ElementTree.fromstring("<eSearchResult><IdList/></eSearchResult>")

        with patch.object(pubmed_stage, "_request_xml", fake_request_xml):
            pubmed_stage.search_pubmed("melanoma", **kwargs)
        return captured["esearch.fcgi"]

    def test_a_bound_becomes_api_parameters(self) -> None:
        parameters = self._esearch_parameters(published_since="2026-01-01")
        self.assertEqual(parameters["datetype"], "pdat")
        self.assertEqual(parameters["mindate"], "2026/01/01")

    def test_the_query_term_never_carries_the_date(self) -> None:
        """The reason the bound lives here: a term matches text, a parameter matches dates.

        Scout's extractor is forbidden from writing a year into a query because an index
        reads it as a word to find. That prohibition is only safe while the bound has
        somewhere else to go.
        """
        parameters = self._esearch_parameters(published_since="2026-01-01")
        self.assertEqual(parameters["term"], "melanoma")
        self.assertNotIn("2026", parameters["term"])

    def test_no_bound_adds_no_parameters(self) -> None:
        parameters = self._esearch_parameters()
        for key in ("datetype", "mindate", "maxdate"):
            self.assertNotIn(key, parameters)

    def test_relevance_ranking_is_kept_inside_the_window(self) -> None:
        """Otherwise a window returns the oldest eligible records rather than the best."""
        self.assertEqual(
            self._esearch_parameters(published_since="2026-01-01")["sort"], "relevance"
        )


#: Helpers that compile a whole query, as opposed to helpers that read one field.
#:
#: Only these are folded into a lane's source for these checks. Every adapter imports
#: `active_tracks` from the same module, so folding in `literature.py` on any import at
#: all made every lane look like it read every dimension the module mentions - which is
#: how the first version of this test called FDA a subject-addressed lane.
QUERY_COMPILERS = ("build_pubmed_query", "build_semantic_scholar_query")


def _lane_source(key: str) -> str:
    """An adapter's own code, plus the helper that compiles its query, if any.

    The literature adapters build their expressions in `literature.py`, so a check
    reading only the adapter would call them liars about dimensions they genuinely use.
    """
    source = _adapter_source(key) + _stage_source(key)
    if any(compiler in source for compiler in QUERY_COMPILERS):
        source += (SOURCES_DIR / "literature.py").read_text()
    return source


def _stage_source(key: str) -> str:
    """Some adapters normalize in a stage; the record may be built there."""
    stage = SOURCES_DIR.parent / "stages" / f"{key}.py"
    return stage.read_text() if stage.exists() else ""


if __name__ == "__main__":
    unittest.main()


class QueryTrackBudgetTests(unittest.TestCase):
    """The split between coverage tracks is a declaration, not eleven coincidences.

    Every config held the identical 8/4/3/3 with nothing stating it, so the balance was
    something eleven files agreed on rather than a decision anyone could review. Moving
    it into `QUERY_TRACK_BUDGET` makes it one thing to read, one thing to change, and a
    config setting a number now *means* that this document type needs a different
    balance.
    """

    #: Every track the extractor runs. A track added without a share would silently
    #: default to zero and never run, which reads as a track that found nothing.
    TRACKS = ("general", "geographic", "counterfactual", "precedent")

    def test_every_track_has_a_declared_share(self) -> None:
        self.assertEqual(sorted(QUERY_TRACK_BUDGET), sorted(self.TRACKS))

    def test_every_share_is_positive(self) -> None:
        """A zero share disables a track, which belongs in a config, not the default."""
        for track, share in QUERY_TRACK_BUDGET.items():
            with self.subTest(track=track):
                self.assertGreater(share, 0)

    def test_the_baseline_track_is_the_largest(self) -> None:
        """Every other track qualifies what `general` establishes, so it cannot be
        smaller than the tracks that depend on it."""
        others = [
            share for track, share in QUERY_TRACK_BUDGET.items() if track != "general"
        ]
        self.assertGreater(QUERY_TRACK_BUDGET["general"], max(others))

    def test_no_config_restates_the_default(self) -> None:
        """A config repeating a default is a second copy that can drift from the first."""
        for path in sorted(CONFIG_DIR.glob("*.yaml")):
            declared = {
                line.split(":")[0]
                for line in path.read_text().splitlines()
                if line.split(":")[0].endswith("queries_per_variable")
            }
            with self.subTest(config=path.name):
                self.assertEqual(declared, set())

    def test_the_configs_receive_the_declared_split(self) -> None:
        for path in sorted(CONFIG_DIR.glob("bmgf_*.yaml")):
            config = load_config(str(path))
            with self.subTest(config=path.name):
                self.assertEqual(
                    (
                        config.queries_per_variable,
                        config.geographic_queries_per_variable,
                        config.counterfactual_queries_per_variable,
                        config.precedent_queries_per_variable,
                    ),
                    (
                        QUERY_TRACK_BUDGET["general"],
                        QUERY_TRACK_BUDGET["geographic"],
                        QUERY_TRACK_BUDGET["counterfactual"],
                        QUERY_TRACK_BUDGET["precedent"],
                    ),
                )
