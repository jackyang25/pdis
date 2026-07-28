from __future__ import annotations

import unittest

from services.chunker.models import ContentBlock, DocumentTypeConfig
from services.chunker.stages.mapper import MapperResponseError, label_blocks


def _blocks() -> list[ContentBlock]:
    return [
        ContentBlock(
            id=f"document:b{index}",
            doc_id="document",
            ordinal=index,
            block_type="paragraph",
            content=f"Content {index}",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        for index in range(2)
    ]


def _config() -> DocumentTypeConfig:
    return DocumentTypeConfig(
        type_key="test",
        org="org",
        source_type="itpp",
        intervention_class="vaccine",
        display_name="Test",
        section_taxonomy=[{"name": "Profile", "description": "Targets"}],
        preamble="Map the document.",
        disambiguation=[],
        include_metadata_label=False,
        include_other_label=False,
    )


class _Client:
    def call_structured(self, _system, _message, *_args, schema, **_kwargs):
        ids = schema["properties"]["labels"]["items"]["properties"]["id"]["enum"]
        return {
            "labels": [
                {"id": block_id, "section_label": "Profile", "confidence": "high"}
                for block_id in ids
            ]
        }


class _DuplicateClient:
    def call_structured(self, *_args, **_kwargs):
        return {
            "labels": [
                {"id": "document:b0", "section_label": "Profile", "confidence": "high"},
                {"id": "document:b0", "section_label": "Profile", "confidence": "high"},
            ]
        }


class ChunkerStructuredMapperTests(unittest.TestCase):
    def test_every_block_receives_one_closed_label(self) -> None:
        result = label_blocks(_blocks(), _config(), _Client(), max_tokens=4000)
        self.assertEqual([block.section_label for block in result], ["Profile", "Profile"])

    def test_duplicate_block_ids_fail_the_mapping_boundary(self) -> None:
        with self.assertRaises(MapperResponseError):
            label_blocks(_blocks(), _config(), _DuplicateClient(), max_tokens=4000)


if __name__ == "__main__":
    unittest.main()
