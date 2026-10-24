"""How much one model request may carry, checked before a stage fans out.

Nothing bounded a request before this. Screener's selection sends every page image of a
document with every question, Inspector's whole-document rubrics and Aligner's two stages
send a whole document, and a large enough upload reached the provider as a context-length
error on the first of dozens of calls - after the parse, and once per worker. A stage now
measures the request it is about to repeat and refuses the run with a code first.

Refused rather than trimmed. A request cut to fit would be answered as though it were
the whole document, which is the failure every tool's contract exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RequestBudget:
    """The most one request may carry: text characters, images, and image bytes."""

    max_text_chars: int
    max_images: int
    max_image_bytes: int


#: About 150k tokens of text, well inside both tiers' context, and the images a
#: provider accepts in one request with room for the text beside them (OpenAI takes at
#: most 500 images and 50 MB per request; base64 adds a third to the bytes below).
DEFAULT_REQUEST_BUDGET = RequestBudget(
    max_text_chars=600_000, max_images=200, max_image_bytes=30_000_000,
)


class RequestTooLargeError(ValueError):
    """A request a stage was about to send exceeds its budget. An input fact, not a model failure."""

    code = "request_too_large"


def image_bytes(images: Iterable[dict[str, str]]) -> int:
    """Decoded bytes of base64 data-URL images, without decoding them."""
    total = 0
    for image in images:
        encoded = image.get("data_url", "").partition(";base64,")[2]
        total += len(encoded) * 3 // 4
    return total


def check_request(
    subject: str,
    *,
    text: str,
    images: list[dict[str, str]] | None = None,
    budget: RequestBudget = DEFAULT_REQUEST_BUDGET,
) -> None:
    """Raise :class:`RequestTooLargeError` naming ``subject`` if the request is over budget."""
    images = images or []
    checks = (
        (len(text), budget.max_text_chars, "characters of text"),
        (len(images), budget.max_images, "images"),
        (image_bytes(images), budget.max_image_bytes, "bytes of images"),
    )
    for size, limit, what in checks:
        if size > limit:
            raise RequestTooLargeError(
                f"{subject} would send {size:,} {what}, more than one request may carry "
                f"({limit:,}). Split the document or supply fewer pages. [{RequestTooLargeError.code}]"
            )
