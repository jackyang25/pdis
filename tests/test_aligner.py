from __future__ import annotations

import json
import unittest

from services.aligner import AlignmentUnit, load_config
from services.aligner.contract import validate_result_contract
from services.aligner.models import (
    AlignmentDocument,
    AlignmentResult,
)
from services.aligner.stages.extractor import extract_units
from services.aligner.stages.linker import align_units
from services.chunker import ContentBlock


class StaticClient:
    def __init__(self, response: dict) -> None:
        self.response = json.dumps(response)

    def call(self, *_args, **_kwargs) -> str:
        return self.response


def block(block_id: str, ordinal: int, content: str) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id="reference",
        ordinal=ordinal,
        block_type="paragraph",
        content=content,
        heading_stack=[],
        structural_meta={},
        style_hint={},
    )


class AlignerTests(unittest.TestCase):
    def test_config_owns_complete_closed_vocabularies(self) -> None:
        config = load_config()
        self.assertEqual(
            {item.name for item in config.unit_types},
            {"target", "activity", "milestone", "requirement", "dependency", "risk_response"},
        )
        self.assertEqual(
            {item.name for item in config.relations},
            {"aligned", "modified", "conflict", "missing", "introduced"},
        )

    def test_extraction_validates_and_preserves_block_lineage(self) -> None:
        config = load_config()
        blocks = [block("reference:b1", 0, "Reach 80% efficacy."), block("reference:b2", 1, "Run Phase 2.")]
        client = StaticClient(
            {
                "units": [
                    {"statement": "Reach 80% efficacy.", "unit_type": "target", "block_ids": ["reference:b1"]},
                    {"statement": "Reach 80% efficacy", "unit_type": "target", "block_ids": ["reference:b2"]},
                ]
            }
        )
        units = extract_units(
            blocks,
            document_role="reference",
            source_type="itpp",
            config=config,
            llm_client=client,
            max_tokens=1000,
        )
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].block_ids, ["reference:b1", "reference:b2"])
        self.assertEqual(units[0].document_id, "reference")

        single_source = StaticClient(
            {
                "units": [
                    {"statement": "Reach 80% efficacy.", "unit_type": "target", "block_ids": ["reference:b1"]}
                ]
            }
        )
        single = extract_units(
            blocks,
            document_role="reference",
            source_type="itpp",
            config=config,
            llm_client=single_source,
            max_tokens=1000,
        )
        self.assertEqual(units[0].id, single[0].id)

    def test_extraction_fails_closed_on_invented_lineage(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unit extraction failed"):
            extract_units(
                [block("reference:b1", 0, "Reach 80% efficacy.")],
                document_role="reference",
                source_type="itpp",
                config=load_config(),
                llm_client=StaticClient(
                    {
                        "units": [
                            {
                                "statement": "Invented",
                                "unit_type": "target",
                                "block_ids": ["not-a-block"],
                            }
                        ]
                    }
                ),
                max_tokens=1000,
            )

    def test_linking_fills_missing_and_introduced_deterministically(self) -> None:
        config = load_config()
        reference = [
            AlignmentUnit("r1", "reference", "reference", "target", "Reach 80% efficacy", ["reference:b1"]),
            AlignmentUnit("r2", "reference", "reference", "milestone", "Complete Phase 2", ["reference:b2"]),
        ]
        comparison = [
            AlignmentUnit("c1", "comparison", "comparison", "target", "Reach 70% efficacy", ["comparison:b1"]),
            AlignmentUnit("c2", "comparison", "comparison", "activity", "Add a stability study", ["comparison:b2"]),
        ]
        client = StaticClient(
            {
                "links": [
                    {
                        "reference_unit_id": "r1",
                        "comparison_unit_ids": ["c1"],
                        "relation": "modified",
                        "reason": "The efficacy threshold changed from 80% to 70%.",
                    },
                ]
            }
        )
        links, stats = align_units(
            reference,
            comparison,
            config=config,
            llm_client=client,
            max_tokens=1000,
        )
        self.assertEqual([link.relation for link in links], ["modified", "missing", "introduced"])
        self.assertEqual(links[0].reference_block_ids, ["reference:b1"])
        self.assertEqual(links[0].comparison_block_ids, ["comparison:b1"])
        self.assertEqual(stats.reference_units, 2)
        self.assertEqual(stats.comparison_units, 2)
        self.assertEqual(stats.modified, 1)
        self.assertEqual(stats.missing, 1)
        self.assertEqual(stats.introduced, 1)

    def test_final_contract_accepts_an_exhaustive_trace(self) -> None:
        config = load_config()
        reference_block = block("reference:b1", 0, "Reach 80% efficacy")
        comparison_block = ContentBlock(
            id="comparison:b1",
            doc_id="comparison",
            ordinal=0,
            block_type="paragraph",
            content="Reach 70% efficacy",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        reference = AlignmentUnit(
            "r1", "reference", "reference", "target", "Reach 80% efficacy", ["reference:b1"]
        )
        comparison = AlignmentUnit(
            "c1", "comparison", "comparison", "target", "Reach 70% efficacy", ["comparison:b1"]
        )
        links, stats = align_units(
            [reference],
            [comparison],
            config=config,
            llm_client=StaticClient(
                {
                    "links": [
                        {
                            "reference_unit_id": "r1",
                            "comparison_unit_ids": ["c1"],
                            "relation": "modified",
                            "reason": "The target changed.",
                        }
                    ]
                }
            ),
            max_tokens=1000,
        )
        result = AlignmentResult(
            reference_document=AlignmentDocument("reference", "reference", "itpp", "iTPP"),
            comparison_document=AlignmentDocument("comparison", "comparison", "ctpp", "cTPP"),
            units=[reference, comparison],
            links=links,
            stats=stats,
            org="org",
            intervention_class="vaccine",
            indication="malaria",
            unit_types=config.unit_types,
            relations=config.relations,
            blocks=[reference_block, comparison_block],
        )
        validate_result_contract(result, config)


if __name__ == "__main__":
    unittest.main()
