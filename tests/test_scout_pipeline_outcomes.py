"""Pipeline-level outcomes: stamped provenance, runs that stop rather than conclude, and
failures kept to the field they happened to."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from services.chunker import ContentBlock
from services.scout import pipeline
from services.scout.models import (
    Attribute,
    DocumentContextValidation,
    DocumentSpan,
    Insight,
    QuantitativeLedger,
    RetrievalScopeLedger,
    ScoutResult,
    FunnelStats,
)
from services.searcher import Finding
from shared.errors import ModelResponseError


class _Stop(Exception):
    def __init__(self, insights):
        super().__init__("stop")
        self.insights = insights


def _block() -> ContentBlock:
    return ContentBlock(
        id="doc/b-0001", doc_id="doc", ordinal=1, block_type="paragraph",
        content="Efficacy above 80%.", heading_stack=[], structural_meta={}, style_hint={},
    )


def _attribute() -> Attribute:
    return Attribute(
        name="efficacy",
        description="Efficacy target",
        block_ids=["doc/b-0001"],
        document_target="Efficacy above 80%.",
        document_spans=[DocumentSpan(quote="Efficacy above 80%.", block_ids=["doc/b-0001"])],
        target_resolved=True,
    )


def _prepared() -> ScoutResult:
    return ScoutResult(
        matches=[], assessments=[],
        stats=FunnelStats(queries=0, findings=0, unique_findings=0, insights=0,
                          matches=0, assessments=0),
        variables=[_attribute()],
        blocks=[_block()],
        context_validation=DocumentContextValidation(
            status="match", configured_indication="group b streptococcus"),
        phase="target_review",
        retrieval_scope=RetrievalScopeLedger.of(
            condition=("group b streptococcus", "header"),
            intervention=("monoclonal antibody", "header"),
        ),
    )


class ContinuationStampTests(unittest.TestCase):
    def test_insights_carry_the_stored_tags_and_prompts_read_the_search_term(self) -> None:
        finding = Finding(url="https://example.test/a", title="A", excerpt="x",
                          source="pubmed", query="q", retrieved_at=datetime.now(timezone.utc))
        seen: dict = {}

        def extract(*_args, indication, intervention_class, **_kwargs):
            seen.update(indication=indication, intervention_class=intervention_class)
            return [Insight(statement="A fact.", supporting_findings=[finding],
                            attribute_ref="efficacy")], [], {}

        def stop(_contexts, insights, *_args, **_kwargs):
            raise _Stop(insights)

        with (
            patch.object(pipeline, "validate_result_contract", side_effect=lambda result: result),
            patch.object(pipeline, "finalize_quantitative_document_review",
                         return_value=([_attribute()], QuantitativeLedger())),
            # Resolved before review and carried on the draft: never re-read here.
            patch.object(pipeline, "resolve_retrieval_scope",
                         side_effect=AssertionError("scope re-read in the continuation")),
            patch.object(pipeline, "_extract_queries_all_variables",
                         return_value={"efficacy": [object()]}),
            patch.object(pipeline, "build_retrieval_intents", return_value=[]),
            patch.object(pipeline, "plan_requests", return_value=[]),
            patch.object(pipeline, "build_program_intents", return_value=[]),
            patch.object(pipeline, "_search_all",
                         return_value=({"efficacy": [finding]}, 1, [])),
            patch.object(pipeline, "read_announcements"),
            patch.object(pipeline, "reconcile_projection_names", return_value=({}, None)),
            patch.object(pipeline, "build_development_landscape", return_value=[]),
            patch.object(pipeline, "build_safety_observations", return_value=[]),
            patch.object(pipeline, "classify_projection_relationships", return_value=([], [])),
            patch.object(pipeline, "_extract_insights_all_variables", side_effect=extract),
            patch.object(pipeline, "_classify_drift_all", side_effect=stop),
        ):
            with self.assertRaises(_Stop) as stopped:
                pipeline.continue_pipeline(
                    _prepared(), config=SimpleNamespace(sources=(), drift_framing=""),
                    openai_client=object(),
                    quantitative_mapping_client=object(), retrieval_runtime=object(),
                    org="bmgf", source_type="itpp",
                    intervention_class="monoclonal_antibody",
                    indication="group_b_streptococcus",
                )

        insight = stopped.exception.insights[0]
        self.assertEqual(insight.indication, "group_b_streptococcus")
        self.assertEqual(insight.intervention_class, "monoclonal_antibody")
        self.assertEqual(seen, {"indication": "group b streptococcus",
                                "intervention_class": "monoclonal antibody"})


class UnresolvedFieldTests(unittest.TestCase):
    def test_unresolved_fields_stop_the_run_instead_of_finishing_empty(self) -> None:
        unresolved = Attribute(name="efficacy", description="Efficacy target",
                               target_resolved=False,
                               target_resolution_reason="No decision was returned.")
        context = DocumentContextValidation(status="match", configured_indication="malaria")
        with (
            patch.object(pipeline, "_parse_all_docs", return_value=[_block()]),
            patch.object(pipeline, "validate_document_context", return_value=context),
            patch.object(pipeline, "_resolve_units", return_value=[unresolved]),
            patch.object(pipeline, "resolve_document_targets", return_value=[unresolved]),
        ):
            with self.assertRaisesRegex(ModelResponseError, "efficacy"):
                pipeline.run_pipeline(
                    ["doc.docx"], config=object(), openai_client=object(),
                    quantitative_mapping_client=object(), retrieval_runtime=object(),
                    org="bmgf", source_type="itpp", intervention_class="vaccine",
                    indication="malaria",
                )


class EmptyCohortTests(unittest.TestCase):
    def test_an_empty_cohort_states_no_meeting_rate(self) -> None:
        from services.scout.models import NumericExpression, QuantitativeFieldLink, QuantitativeTarget
        from services.scout.stages.conformity import empty_conformity_scores
        from tests.test_scout_lineage import comparison_contract, semantic_profile

        target = QuantitativeTarget(
            field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines",
                                               reason="Test fixture.")],
            expression=NumericExpression(kind="bound", value=80, comparator=">=", unit="%"),
            role="threshold",
            quote="Efficacy above 80%.",
            doc_block_ids=["doc/b-0001"],
            semantic_profile=semantic_profile("protective efficacy"),
            comparison_contract=comparison_contract(semantic_profile("protective efficacy")),
        )

        (score,) = empty_conformity_scores([target])

        self.assertIsNone(score.target_meeting_rate)
        self.assertEqual(score.target_meeting_count, 0)


class AvailableConfigTests(unittest.TestCase):
    def test_a_malformed_config_declaring_its_identity_raises(self) -> None:
        import tempfile
        from pathlib import Path

        from services.scout import models

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "bmgf_itpp_vaccine.yaml").write_text("type_key: bmgf_itpp_vaccine\n")
            Path(directory, "CONFIG_TEMPLATE.yaml").write_text("type_key: example_org_itpp_vaccine\n")
            Path(directory, "evidence_methodology.yaml").write_text("calibration: 1\n")
            with patch.object(models, "CONFIGS_DIR", Path(directory)):
                with self.assertRaisesRegex(ValueError, "missing required fields"):
                    models.available_configs()


if __name__ == "__main__":
    unittest.main()


class UnreadFieldTests(unittest.TestCase):
    """One field's evidence failing to be read is that field's, not the run's."""

    @staticmethod
    def _finding(key: str) -> Finding:
        return Finding(url=f"https://example.test/{key}", title=key, excerpt="x", source="pubmed",
                       query="q", retrieved_at=datetime.now(timezone.utc), record_key=f"pubmed:{key}")

    def _extract(self, fail):
        """Insights for every batch, except where `fail(field, batch)` names an exception."""
        def extract(batch, _client, *, attribute_ref, **_kwargs):
            if (error := fail(attribute_ref, batch)) is not None:
                raise error
            return [Insight(statement=f"{attribute_ref} fact", supporting_findings=batch,
                            attribute_ref=attribute_ref)]
        return extract

    def _run(self, fail, findings_by_attribute):
        with (
            patch.object(pipeline, "extract_insights", side_effect=self._extract(fail)),
            patch.object(pipeline, "reconcile_duplicate_insights",
                         side_effect=lambda insights, _client: (insights, [])),
            # One finding per batch, so a field can hold a batch that succeeds and one that fails.
            patch.object(pipeline, "_finding_batches", side_effect=lambda findings: [[f] for f in findings]),
        ):
            return pipeline._extract_insights_all_variables(
                findings_by_attribute, {}, pipeline.RetrievalLineage(()), object(),
                indication="malaria", intervention_class="vaccine",
            )

    def test_a_failed_batch_leaves_its_field_unread_and_the_others_read(self) -> None:
        import httpx
        import openai

        stalled = openai.APITimeoutError(request=httpx.Request("POST", "https://gateway.test"))
        insights, _, unread = self._run(
            lambda field, batch: stalled if batch[0].title == "e2" else None,
            {"efficacy": [self._finding("e1"), self._finding("e2")],
             "safety": [self._finding("s1")]},
        )

        # The failed field's batch that succeeded is set aside with it: judged on part of
        # its evidence, it would read as judged on all of it.
        self.assertEqual([insight.attribute_ref for insight in insights], ["safety"])
        self.assertEqual(set(unread), {"efficacy"})
        self.assertEqual(unread["efficacy"].failure_code, "provider_error")
        self.assertIn("could not be read", unread["efficacy"].reason)
        self.assertIn("timed out", unread["efficacy"].reason)

    def test_an_invalid_answer_keeps_its_code(self) -> None:
        _, _, unread = self._run(
            lambda field, _batch: ModelResponseError("no valid answer") if field == "safety" else None,
            {"efficacy": [self._finding("e1")], "safety": [self._finding("s1")]},
        )
        self.assertEqual(unread["safety"].failure_code, "invalid_model_response")

    def test_a_programming_error_still_stops_the_run(self) -> None:
        with self.assertRaises(KeyError):
            self._run(lambda *_: KeyError("bug"), {"efficacy": [self._finding("e1")]})

    def test_an_unread_field_is_not_assessed_on_grounding_and_precedent_without_a_call(self) -> None:
        unread = {"efficacy": pipeline.UnreadField("Its evidence could not be read: Request timed out.",
                                                   "provider_error")}
        never = AssertionError("an unread field was judged")
        with (
            patch.object(pipeline, "assess_evidence", side_effect=never),
            patch.object(pipeline, "classify_precedent", side_effect=never),
        ):
            assessment, = pipeline._assess_evidence_all_variables(
                [_attribute()], {}, [], object(), indication="malaria",
                intervention_class="vaccine", unread=unread,
            )
            signal, = pipeline._classify_precedent_all_variables(
                [_attribute()], {}, [], object(), indication="malaria",
                intervention_class="vaccine", unread=unread,
            )

        self.assertEqual((assessment.strength, assessment.failure_code), ("not_assessed", "provider_error"))
        self.assertEqual(assessment.reason, unread["efficacy"].reason)
        self.assertEqual((signal.precedent, signal.outcome, signal.failure_code),
                         ("not_assessed", "not_assessed", "provider_error"))
