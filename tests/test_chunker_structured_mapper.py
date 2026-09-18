from __future__ import annotations

import unittest

from services.chunker.models import ContentBlock, DocumentTypeConfig, ImageAsset
from services.chunker.stages.mapper import MapperResponseError, label_blocks


def _blocks(count: int = 2) -> list[ContentBlock]:
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
        for index in range(count)
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
    def __init__(self):
        self.calls = []

    def call_structured(self, _system, _message, *_args, schema, **_kwargs):
        self.calls.append((_system, _message, schema, _kwargs))
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
    def test_split_requests_retain_all_images_and_retry_only_bad_partition(self):
        class RetryClient(_Client):
            def call_structured(self, *args, **kwargs):
                payload = super().call_structured(*args, **kwargs)
                ids = [label["id"] for label in payload["labels"]]
                if ids == ["document:b996"] and not getattr(self, "retried", False):
                    self.retried = True
                    payload["labels"][0]["id"] = "document:b0"
                return payload
        blocks = _blocks(997)
        blocks[0].image = ImageAsset("image/png", "AA==", "hash", "image/png")
        client = RetryClient()
        label_blocks(blocks, _config(), client, max_tokens=4000)
        self.assertEqual(len(client.calls), 3)
        for _, _, schema, kwargs in client.calls:
            self.assertEqual(kwargs["images"], [{"block_id": "document:b0", "data_url": "data:image/png;base64,AA=="}])
            self.assertFalse(schema["additionalProperties"])
        self.assertTrue(all(block.section_label == "Profile" for block in blocks))

    def test_impossible_taxonomy_fails_before_calling_provider(self):
        config = _config()
        config.section_taxonomy = [{"name": f"Section {i}", "description": "Meaning"} for i in range(1000)]
        client = _Client()
        with self.assertRaises(MapperResponseError):
            label_blocks(_blocks(), config, client, max_tokens=4000)
        self.assertEqual(client.calls, [])

    def test_total_schema_string_limit_is_checked_even_for_small_enums(self):
        blocks = _blocks(2)
        for block in blocks:
            block.id = "x" * 70_000 + block.id
        client = _Client()
        label_blocks(blocks, _config(), client, max_tokens=4000)
        self.assertEqual(len(client.calls), 2)
        blocks[0].id = "x" * 120_000
        client = _Client()
        with self.assertRaises(MapperResponseError):
            label_blocks(blocks, _config(), client, max_tokens=4000)
        self.assertEqual(client.calls, [])

    def test_metadata_and_other_labels_also_consume_enum_capacity(self):
        config = _config()
        config.include_metadata_label = True
        config.include_other_label = True
        client = _Client()
        label_blocks(_blocks(995), config, client, max_tokens=4000)
        sizes = [len(call[2]["properties"]["labels"]["items"]["properties"]["id"]["enum"])
                 for call in client.calls]
        self.assertEqual(sorted(sizes), [1, 994])

    def test_splits_only_when_schema_enum_capacity_is_exceeded(self):
        for count, expected_sizes in [(996, [996]), (997, [996, 1]), (1212, [996, 216])]:
            with self.subTest(count=count):
                blocks = _blocks(count)
                client = _Client()
                result = label_blocks(blocks, _config(), client, max_tokens=4000)
                sizes = [len(call[2]["properties"]["labels"]["items"]["properties"]["id"]["enum"])
                         for call in client.calls]
                self.assertEqual(sorted(sizes), sorted(expected_sizes))
                self.assertEqual([b.id for b in result], [b.id for b in blocks])
                self.assertTrue(all(b.section_label == "Profile" for b in result))
                for _, message, _, _ in client.calls:
                    self.assertIn("<content>Content 0</content>", message)
                    self.assertIn(f"<content>Content {count - 1}</content>", message)

    def test_long_block_ids_respect_string_enum_limit_without_splitting_250(self):
        for count, expected_sizes in [(250, [250]), (251, [250, 1])]:
            blocks = _blocks(count)
            for b in blocks:
                b.id = "long-document-name-" * 6 + b.id
            client = _Client()
            label_blocks(blocks, _config(), client, max_tokens=4000)
            sizes = [len(call[2]["properties"]["labels"]["items"]["properties"]["id"]["enum"])
                     for call in client.calls]
            self.assertEqual(sorted(sizes), sorted(expected_sizes))

    def test_failed_later_partition_does_not_publish_partial_labels(self):
        class FailingClient(_Client):
            def call_structured(self, *args, **kwargs):
                payload = super().call_structured(*args, **kwargs)
                if any(label["id"] == "document:b996" for label in payload["labels"]):
                    payload["labels"] = []
                return payload
        blocks = _blocks(997)
        with self.assertRaises(MapperResponseError):
            label_blocks(blocks, _config(), FailingClient(), max_tokens=4000)
        self.assertTrue(all(b.section_label is None for b in blocks))

    def test_every_block_receives_one_closed_label(self) -> None:
        result = label_blocks(_blocks(), _config(), _Client(), max_tokens=4000)
        self.assertEqual([block.section_label for block in result], ["Profile", "Profile"])

    def test_duplicate_block_ids_fail_the_mapping_boundary(self) -> None:
        with self.assertRaises(MapperResponseError):
            label_blocks(_blocks(), _config(), _DuplicateClient(), max_tokens=4000)


if __name__ == "__main__":
    unittest.main()
