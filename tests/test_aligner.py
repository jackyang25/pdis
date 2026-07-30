from __future__ import annotations

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
        self.response = response

    def call_structured(self, *_args, **_kwargs) -> dict:
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
        # Answer per request: a link may only cite a unit the request carried.
        class _PerRequestClient(StaticClient):
            def call_structured(self, _system_prompt, message, *_args, **_kwargs) -> dict:
                if "r1" not in message:
                    return {"links": []}
                return {
                    "links": [
                        {
                            "reference_unit_id": "r1",
                            "comparison_unit_ids": ["c1"],
                            "relation": "modified",
                            "reason": "The efficacy threshold changed from 80% to 70%.",
                        },
                    ]
                }

        client = _PerRequestClient({"links": []})
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

    def test_each_reference_unit_is_linked_in_its_own_request(self) -> None:
        """One relation per reference unit, judged against the candidate pool."""
        class _RecordingClient(StaticClient):
            def __init__(self, payload) -> None:
                super().__init__(payload)
                self.messages: list[str] = []

            def call_structured(self, system_prompt, message, *args, **kwargs) -> dict:
                self.messages.append(message)
                return super().call_structured(system_prompt, message, *args, **kwargs)

        config = load_config()
        reference = [
            AlignmentUnit(
                f"ref-unit-{index}", "reference", "reference", "target",
                f"Reference statement {index}", [f"reference:b{index}"],
            )
            for index in range(3)
        ]
        comparison = [
            AlignmentUnit(
                "cmp-unit-0", "comparison", "comparison", "target",
                "Comparison statement", ["comparison:b0"],
            )
        ]
        client = _RecordingClient({"links": []})

        align_units(
            reference,
            comparison,
            config=config,
            llm_client=client,
            max_tokens=1000,
        )

        # Retries repeat a request, so assert on scope rather than call count.
        mentioned = [
            [unit.id for unit in reference if unit.id in message]
            for message in client.messages
        ]
        self.assertTrue(
            all(len(ids) == 1 for ids in mentioned),
            f"a request carried more than one reference unit: {mentioned}",
        )
        self.assertEqual(
            {ids[0] for ids in mentioned},
            {"ref-unit-0", "ref-unit-1", "ref-unit-2"},
        )

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


class SchemaBoundContractTests(unittest.TestCase):
    """Aligner must use the suite's schema-bound client contract."""

    class _StructuredOnlyClient:
        """Implements only `call_structured`, like every other service's client."""

        def __init__(self, payload: dict) -> None:
            self.payload = payload
            self.schemas: list[dict] = []

        def call_structured(self, _system, _message, _max_tokens, *, schema, **_kwargs):
            self.schemas.append(schema)
            return self.payload

    def test_extraction_drives_a_schema_bound_client(self) -> None:
        config = load_config()
        source = block("reference:b1", 1, "Reach 80% efficacy by 2027.")
        client = self._StructuredOnlyClient({
            "units": [{
                "statement": "Reach 80% efficacy by 2027.",
                "unit_type": "target",
                "block_ids": ["reference:b1"],
            }]
        })

        units = extract_units(
            [source],
            source_type="itpp",
            document_role="reference",
            config=config,
            llm_client=client,
            max_tokens=1000,
        )

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].statement, "Reach 80% efficacy by 2027.")
        # The block lineage is constrained by the schema, not by prose validation.
        block_ids = client.schemas[0]["properties"]["units"]["items"]["properties"][
            "block_ids"
        ]["items"]["enum"]
        self.assertEqual(block_ids, ["reference:b1"])
