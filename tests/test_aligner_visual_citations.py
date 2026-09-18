"""Visual lineage is not a quotation of the parser's image marker."""

import unittest

from services.chunker import ImageAsset
from services.aligner.context import read_spans
from services.aligner.stages.requirements import (
    _parse_payload as read_requirements,
    extract_requirements,
)
from services.aligner.stages.assessor import (
    _parse_payload as read_assessment,
    assess_requirement,
)
from services.aligner.contract import validate_result_contract
from services.aligner.models import AlignmentFinding, load_config
from tests.test_aligner import block, result


def visual(block_id, doc_id):
    source = block(block_id, doc_id)
    source.block_type = "image"
    source.content = "[image]"
    source.image = ImageAsset(media_type="image/png", data_base64="AA==", sha256="test",
                              source_media_type="image/png", width=1, height=1)
    return source


class RetryClient:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **kwargs
    ):
        self.calls.append({
            "system": system_prompt,
            "user": user_message,
            "schema_name": schema_name,
            "schema": schema,
            "images": kwargs.get("images"),
        })
        return self.payloads[len(self.calls) - 1]


class AlignerVisualCitationTests(unittest.TestCase):
    def test_requirement_retry_accepts_a_retained_visual_instead_of_text(self):
        source = visual("a/visual", "a")
        client = RetryClient(
            {"requirements": [{
                "text": "The milestone is in 2027.", "spans": [], "visual_block_ids": [],
            }]},
            {"requirements": [{
                "text": "The milestone is in 2027.",
                "spans": [],
                "visual_block_ids": [source.id],
            }]},
        )

        requirements = extract_requirements(
            edge_id="a-b", role="A profile.", question="?", blocks=[source],
            llm_client=client, max_tokens=1000,
        )

        self.assertEqual(requirements[0].visual_block_ids, (source.id,))
        retry = client.calls[1]["user"]
        self.assertIn("exact [line:N] ranges in `spans`", retry)
        self.assertIn("retained visual IDs in `visual_block_ids`", retry)

    def test_assessment_retry_accepts_a_retained_visual_instead_of_text(self):
        reference = visual("a/visual", "a")
        comparison = visual("b/visual", "b")
        requirement = read_requirements({"requirements": [{
            "text": "The milestone is in 2027.",
            "spans": [],
            "visual_block_ids": [reference.id],
        }]}, edge_id="a-b", blocks=[reference])[0]
        client = RetryClient(
            {"verdict": "meets", "statement": "The milestone is scheduled in 2027.",
             "spans": [], "visual_block_ids": []},
            {"verdict": "meets", "statement": "The milestone is scheduled in 2027.",
             "spans": [], "visual_block_ids": [comparison.id]},
        )

        finding = assess_requirement(
            requirement, edge_id="a-b", role="A candidate.", question="?",
            blocks=[comparison], llm_client=client, max_tokens=1000,
        )

        self.assertEqual(finding.reference_visual_block_ids, [reference.id])
        self.assertEqual(finding.comparison_visual_block_ids, [comparison.id])
        retry = client.calls[1]["user"]
        self.assertIn("exact [line:N] ranges in `spans`", retry)
        self.assertIn("retained visual IDs in `visual_block_ids`", retry)

    def test_contract_checks_visual_asset_and_document_side(self):
        reference = visual("itpp_file/visual", "itpp_file")
        comparison = visual("ctpp_file/visual", "ctpp_file")
        finding = AlignmentFinding(requirement_id="requirement", edge_id="itpp-to-ctpp",
            requirement="Milestone in 2027.", reference_spans=[], verdict="meets",
            statement="The milestone is scheduled in 2027.",
            reference_visual_block_ids=[reference.id], comparison_visual_block_ids=[comparison.id])
        held = result(blocks=[reference, comparison], findings=[finding])
        self.assertIs(validate_result_contract(held, load_config()), held)
        finding.comparison_visual_block_ids = [reference.id]
        with self.assertRaises(ValueError):
            validate_result_contract(held, load_config())
        finding.comparison_visual_block_ids = [comparison.id]
        comparison.image = None
        with self.assertRaises(ValueError):
            validate_result_contract(held, load_config())

    def test_visual_only_requirement_and_assessment_keep_separate_lineage(self):
        reference = visual("a/visual", "a")
        comparison = visual("b/visual", "b")
        requirements = read_requirements({"requirements": [{
            "text": "The milestone is in 2027.", "spans": [], "visual_block_ids": [reference.id],
        }]}, edge_id="a-b", blocks=[reference])
        requirement = requirements[0]
        finding = read_assessment({"verdict": "meets", "statement": "The milestone is scheduled in 2027.",
            "spans": [], "visual_block_ids": [comparison.id]}, requirement=requirement,
            edge_id="a-b", blocks=[comparison])
        self.assertEqual(finding.reference_visual_block_ids, [reference.id])
        self.assertEqual(finding.comparison_visual_block_ids, [comparison.id])
        self.assertEqual(finding.reference_spans, [])
        self.assertEqual(finding.comparison_spans, [])

    def test_image_marker_is_not_a_readable_text_span(self):
        source = visual("a/visual", "a")
        self.assertEqual(read_spans([{"block_id": source.id, "start_line": 1, "end_line": 1}], [source]), [])

    def test_missing_visual_asset_cannot_be_cited(self):
        source = visual("a/visual", "a")
        source.image = None
        with self.assertRaises(ValueError):
            read_requirements({"requirements": [{"text": "The milestone is in 2027.",
                "spans": [], "visual_block_ids": [source.id]}]}, edge_id="a-b", blocks=[source])
