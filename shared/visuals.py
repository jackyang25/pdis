"""The one way a document visual is labelled for a model.

AGENTS.md requires every multimodal call to label an image with its exact block ID.
Tool pipelines and the Assistant both build their image parts here, so the label has
one wording everywhere. Tool pipelines' prompts depend on this exact text.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

#: How finely the provider looks at an image. `high` reads a page's text and a chart's
#: figures; `low` is one small view of the whole image, enough to tell what a visual is
#: and whether it bears on a question, at a fraction of the cost. A stage chooses.
ImageDetail = Literal["low", "high"]


def labelled_image_parts(
    images: Iterable[tuple[str, str] | tuple[str, str, ImageDetail]],
) -> list[dict[str, Any]]:
    """`(block_id, data_url[, detail])` as label-then-image parts; detail defaults to high."""
    parts: list[dict[str, Any]] = []
    for image in images:
        block_id, data_url = image[0], image[1]
        detail = image[2] if len(image) > 2 else "high"
        parts.append({"type": "text", "text": f"Visual for document block [{block_id}]:"})
        parts.append({"type": "image_url", "image_url": {"url": data_url, "detail": detail}})
    return parts
