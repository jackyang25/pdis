"""The one way a document visual is labelled for a model.

AGENTS.md requires every multimodal call to label an image with its exact block ID.
Tool pipelines and the Assistant both build their image parts here, so the label has
one wording everywhere. Tool pipelines' prompts depend on this exact text.
"""

from __future__ import annotations

from typing import Any, Iterable


def labelled_image_parts(images: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    """`(block_id, data_url)` pairs as label-then-image content parts."""
    return [
        part
        for block_id, data_url in images
        for part in (
            {"type": "text", "text": f"Visual for document block [{block_id}]:"},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        )
    ]
