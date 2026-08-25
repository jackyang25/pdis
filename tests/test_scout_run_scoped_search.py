"""A search planned from the run's own scope, not from a variable.

The development landscape and the burden indicators are asked about the *run*: its
condition, its intervention class. Those intents carry `PROGRAM_SCOPE_KEY` as their scope
because there is no variable that owns them, and the projections they produce reach the
contract with the same sentinel, which two checks there already accept.

The trace that produced them did not. So any run whose burden lane actually fired was
rejected by its own contract:

    search trace 'indicator_name_contains:polio' references unknown field 'program'

Nothing exercised it, because no test built a run-scoped `SearchTrace` and validated it.
"""

from __future__ import annotations

import unittest

from services.scout.contract import validate_result_contract
from dataclasses import replace

from services.scout.models import (
    ConformityScore,
    DocumentSpan,
    NumericExpression,
    PROGRAM_QUERY_SETS,
    PROGRAM_SCOPE_KEY,
    VALID_ATTRIBUTE_QUERY_TRACKS,
    valid_query_tracks,
    QuantitativeFieldLink,
    QuantitativeLedgerReview,
    QuantitativeTarget,
    SearchTrace,
)

from tests.test_scout_contract import _result as minimal_result
from tests.test_scout_lineage import comparison_contract, semantic_profile


class RunScopedSearchTraceTests(unittest.TestCase):
    def _with_trace(self, **over) -> object:
        result = minimal_result()
        result.search_plan = [
            SearchTrace(
                attribute_ref=over.pop("attribute_ref", PROGRAM_SCOPE_KEY),
                lane="who_gho",
                query="indicator_name_contains:polio",
                intent_ids=["intent-1"],
                input_queries=["polio"],
                **over,
            )
        ]
        return result

    def test_a_run_scoped_search_is_accepted(self):
        """The bug. A burden lane firing was enough to fail the whole result."""
        validate_result_contract(self._with_trace())

    def test_a_run_scoped_search_still_cannot_claim_a_passage(self):
        """The sentinel is a hole in the field check; it is not one in the lineage checks.

        A search built from the configured condition never read a document block, so
        claiming one would be a lineage the run cannot support.
        """
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(doc_block_ids=["document/b-0001"]))
        self.assertIn("document blocks", str(raised.exception))

    def test_a_run_scoped_search_still_cannot_claim_a_target(self):
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(target_ids=["qt-1"]))
        self.assertIn("targets", str(raised.exception))

    def test_a_variable_scoped_search_still_names_a_real_variable(self):
        """Unchanged. Only the one sentinel is exempt, not any unknown string."""
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(attribute_ref="not_a_field"))
        self.assertIn("references unknown field", str(raised.exception))


if __name__ == "__main__":
    unittest.main()



class NumericQueryBlockTests(unittest.TestCase):
    """A search planned from a target, carrying that target's passages.

    `query_extractor` builds a numeric query straight from `target_blocks[target_id]`, and a
    target can cite a passage its field's own extraction never listed: a table row elsewhere
    in the document that states the number. Checking a trace's blocks against the field alone
    rejected the run:

        search trace '... reported numeric results' document blocks contain unknown IDs:
        BNT.TPP Draft VGP 18Dec2025/b-0008
    """

    def _scenario(self):
        """A field whose blocks and whose target's blocks do not overlap.

        That is the shape the pipeline produces and the contract rejected. The second block
        already exists on the document and in the ledger, so it is a passage the run can
        point at, not an invented id.
        """
        result = minimal_result()
        field_block = result.blocks[0].id
        target_block = result.blocks[1].id
        profile = semantic_profile("injections administered")
        span = DocumentSpan(quote="No more than 4 injections.", block_ids=[target_block])
        target = QuantitativeTarget(
            field_links=[
                QuantitativeFieldLink(
                    attribute_ref=result.variables[0].name,
                    relation="defines",
                    reason="Test fixture.",
                )
            ],
            expression=NumericExpression(kind="bound", value=4, comparator="<=", unit="injections"),
            role="threshold",
            quote="No more than 4 injections.",
            doc_block_ids=[target_block],
            semantic_profile=profile,
            comparison_contract=comparison_contract(profile),
            # A specified semantic slot has to cite the passage it was read from, so the
            # profile above cannot claim a measure the document never stated.
            provenance_spans=[span],
            semantic_provenance={"measure": [span]},
            review_status="approved",
        )
        result.variables = [
            replace(
                variable,
                block_ids=[field_block],
                quantitative_target_ids=[target.id] if index == 0 else [],
                quantitative_target_status="present" if index == 0 else "not_applicable",
            )
            for index, variable in enumerate(result.variables)
        ]
        result.quantitative_ledger = replace(
            result.quantitative_ledger,
            status="complete",
            block_ids=[field_block, target_block],
            targets=[target],
            # Every target must be covered by a statement review, so the ledger states where
            # the number came from as well as what it says.
            reviews=[
                QuantitativeLedgerReview(
                    unit_id="unit-1",
                    block_id=target_block,
                    quote="No more than 4 injections.",
                    classification="target",
                    attribute_refs=[result.variables[0].name],
                    reason="Mapped target.",
                    target_ids=[target.id],
                )
            ],
        )
        # Every target owes a calibration that mirrors it exactly, so the fixture states one
        # rather than leaving the ledger half-built.
        result.conformity = [
            ConformityScore(
                target_id=target.id,
                attribute_refs=list(target.analysis_attribute_refs),
                target_role=target.role,
                target_value=target.value,
                comparator=target.comparator,
                unit=target.unit,
                target_label=target.label,
                target_quote=target.quote,
                doc_block_ids=list(target.doc_block_ids),
                target_meeting_count=0,
                target_meeting_rate=0.0,
                verdict="No comparable measurement was found.",
            )
        ]
        return result, target, field_block, target_block

    def _trace(self, result, *, blocks, target_ids):
        result.search_plan = [
            SearchTrace(
                attribute_ref=result.variables[0].name,
                lane="pubmed",
                query="a numeric query reported numeric results",
                doc_block_ids=blocks,
                target_ids=target_ids,
                intent_ids=["intent-1"],
                input_queries=["numbers"],
            )
        ]
        return result

    def test_a_numeric_search_may_cite_its_target_passage(self):
        """The bug. The target's own blocks are already checked against the document."""
        result, target, _, target_block = self._scenario()
        validate_result_contract(
            self._trace(result, blocks=[target_block], target_ids=[target.id])
        )

    def test_a_search_naming_no_target_is_still_held_to_its_field(self):
        """Unchanged. The widening applies only to passages a named target owns."""
        result, _, _, target_block = self._scenario()
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._trace(result, blocks=[target_block], target_ids=[]))
        self.assertIn("document blocks", str(raised.exception))

    def test_naming_a_target_does_not_admit_an_arbitrary_block(self):
        """The exemption is that target's passages, not any passage."""
        result, target, _, _ = self._scenario()
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(
                self._trace(result, blocks=["document/b-9999"], target_ids=[target.id])
            )
        self.assertIn("document blocks", str(raised.exception))

    def test_a_merged_query_carries_both_and_is_admitted(self):
        """The third path, and the reason the rule is a union rather than a choice.

        `query_extractor` collapses two queries with the same text into one, taking the union
        of their blocks *and* of their target ids together. So a merged query can hold a
        field passage and a target passage at once, and it names the target either way.
        """
        result, target, field_block, target_block = self._scenario()
        validate_result_contract(
            self._trace(result, blocks=[field_block, target_block], target_ids=[target.id])
        )

    def test_the_field_own_blocks_are_still_admitted(self):
        result, target, field_block, _ = self._scenario()
        validate_result_contract(
            self._trace(result, blocks=[field_block], target_ids=[target.id])
        )


class EveryProgramLaneSurvivesTheContractTests(unittest.TestCase):
    """The audit these three fixes should have started with.

    A run-scoped search failed the contract in *four* separate checks in one loop, and each
    was found only when a run happened to fire the lane that triggered it:

        1. the field check      -> "references unknown field 'program'"
        2. the block check      -> KeyError on the sentinel
        3. the target check     -> the same
        4. the track check      -> "has an unknown query track"

    One omission - program-scoped intents were added after the contract's trace loop was
    written, and the loop was never revisited - surfacing four times, three of them patched
    reactively. This builds a trace exactly as `intent_builder` and the pipeline do, for every
    program query set and every lane each set declares, so a fifth check cannot be found by a
    user instead of by a test.
    """

    def test_every_program_query_set_and_lane_passes(self):
        for name, query_set in PROGRAM_QUERY_SETS.items():
            for lane in query_set.lanes:
                with self.subTest(program_set=name, lane=lane):
                    result = minimal_result()
                    result.search_plan = [
                        SearchTrace(
                            # As `intent_builder` builds it: the sentinel as the scope, and
                            # the query set's own name as the track.
                            attribute_ref=PROGRAM_SCOPE_KEY,
                            lane=lane,
                            query=f"a {name} query on {lane}",
                            tracks=[name],
                            intent_ids=["intent-1"],
                            input_queries=["a phrase"],
                        )
                    ]
                    validate_result_contract(result)

    def test_a_program_track_on_a_variable_scoped_trace_also_passes(self):
        """The vocabulary is one set, not two gates.

        A track is a track. Splitting the check by scope would be a fifth thing to keep in
        step, and the scope is already asserted by the field and lineage checks above.
        """
        result = minimal_result()
        result.search_plan = [
            SearchTrace(
                attribute_ref=result.variables[0].name,
                lane="web",
                query="a query",
                tracks=["events"],
                intent_ids=["intent-1"],
                input_queries=["a phrase"],
            )
        ]
        validate_result_contract(result)

    def test_an_invented_track_is_still_rejected(self):
        """Widening the vocabulary must not empty it."""
        result = minimal_result()
        result.search_plan = [
            SearchTrace(
                attribute_ref=PROGRAM_SCOPE_KEY,
                lane="web",
                query="a query",
                tracks=["not_a_track"],
                intent_ids=["intent-1"],
                input_queries=["a phrase"],
            )
        ]
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(result)
        self.assertIn("unknown query track", str(raised.exception))

    def test_the_track_vocabulary_is_derived_from_the_program_sets(self):
        """So adding a program query set cannot leave the contract behind.

        This is the check that makes the other three unnecessary next time: a new set widens
        the vocabulary by construction rather than by someone remembering.
        """
        self.assertEqual(
            valid_query_tracks(),
            frozenset(VALID_ATTRIBUTE_QUERY_TRACKS) | frozenset(PROGRAM_QUERY_SETS),
        )
        for name in PROGRAM_QUERY_SETS:
            self.assertIn(name, valid_query_tracks(), name)
