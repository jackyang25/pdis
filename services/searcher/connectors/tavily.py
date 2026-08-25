"""Minimal client for Tavily's search API.

Shaped like `ToolUniverseHTTPConnector` and for the same reason: the connector executes one
request and returns parsed JSON, while the source adapter owns query grammar and turns
records into Findings. Nothing here knows what a Finding is.

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
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

#: Tavily's public endpoint. Overridable for a proxy, validated like any other base URL.
DEFAULT_BASE_URL = "https://api.tavily.com"

#: `advanced` costs two credits and `basic` one. Advanced is the default because the reason to
#: use Tavily at all is the quality of the extracted content, and basic depth returns less of
#: it: paying half as much for the thing you came for is not a saving.
DEFAULT_SEARCH_DEPTH = "advanced"

VALID_SEARCH_DEPTHS = frozenset({"basic", "advanced"})


@dataclass(frozen=True)
class TavilyHTTPConnector:
    """Execute one Tavily search and return its parsed JSON."""

    api_key: str
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
            # The extracted page text, which is the whole reason for this lane. Without it a
            # result carries a title and a URL and the excerpt is empty, which is worse than
            # the paraphrase it replaces.
            "include_raw_content": False,
            # No generated summary. A model's answer about the results is exactly what this
            # lane exists to stop carrying, and it costs an extra credit.
            "include_answer": False,
        }
        request = Request(
            f"{self.base_url.rstrip('/')}/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                # Header auth, not the body. The key never enters a logged payload.
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # The status, never the body: an error body can echo the query and the key.
            raise RuntimeError(f"Tavily HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Tavily is unavailable: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Tavily returned invalid JSON") from exc
