"""Minimal client for Tavily's search API.

A connector because the lane cannot run without the deployment's paid key and its options
(depth, endpoint, timeout): the API builds it and injects it. It executes one request and
returns parsed JSON, while the source adapter owns query grammar and turns records into
Findings. Nothing here knows what a Finding is.

Why Tavily exists beside the `web` lane at all. The `web` lane is OpenAI's Responses API with
its `web_search` tool: a model is asked a question, it searches internally, writes an answer,
and the lane harvests the URLs it happened to cite. Measured on a real run that produced 1.4
findings per search with half of them returning nothing, against 18.9 for PubMed. Worse, the
excerpt it yields is *the model's own sentence about the page*, sometimes in the language of
the query rather than of the source, so a passage quoted downstream is a paraphrase presented
as a quotation. Tavily returns ranked results with content extracted from the page, which is
what an excerpt is supposed to be.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..transport import fetch_json

#: Tavily's public endpoint. A test may construct the connector with another.
DEFAULT_BASE_URL = "https://api.tavily.com"

#: `advanced` costs two credits and `basic` one. Advanced is the default because the reason to
#: use Tavily at all is the quality of the extracted content, and basic depth returns less of
#: it: paying half as much for the thing you came for is not a saving.
DEFAULT_SEARCH_DEPTH = "advanced"

VALID_SEARCH_DEPTHS = frozenset({"basic", "advanced"})


@dataclass(frozen=True)
class TavilyHTTPConnector:
    """Execute one Tavily search and return its parsed JSON."""

    # Kept out of repr, so a logged or failing connector never prints its credential.
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    search_depth: str = DEFAULT_SEARCH_DEPTH
    timeout_seconds: float = 30.0
    #: Results per request. Tavily caps this per plan; the adapter's own limit applies too.
    max_results: int = 10

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Tavily requires an API key")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Tavily base URL must be an absolute HTTP(S) URL")
        if self.search_depth not in VALID_SEARCH_DEPTHS:
            raise ValueError(
                f"Tavily search depth must be one of {sorted(VALID_SEARCH_DEPTHS)}"
            )
        if self.timeout_seconds <= 0:
            raise ValueError("Tavily timeout must be positive")
        if self.max_results <= 0:
            raise ValueError("Tavily max results must be positive")

    def search(self, query: str, *, max_results: int | None = None) -> Any:
        """Run one search. Raises on transport or API failure; the caller decides."""
        payload = {
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max_results or self.max_results,
            # Not the whole page. Each result's `content` - Tavily's extract of the passage
            # relevant to the query - is always returned and is what the excerpt reads. A
            # page's raw text opens with its navigation, and the excerpt is a bounded prefix.
            "include_raw_content": False,
            # No generated summary. A model's answer about the results is exactly what this
            # lane exists to stop carrying, and it costs an extra credit.
            "include_answer": False,
        }
        return fetch_json(
            f"{self.base_url.rstrip('/')}/search",
            provider="Tavily",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                # Header auth, not the body. The key never enters a logged payload.
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
            timeout=self.timeout_seconds,
            # The error body's own message is kept (which limit, which plan), with the key
            # removed should the body ever echo it.
            secrets=(self.api_key,),
        )
