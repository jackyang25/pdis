"""Shared Anthropic client.

One provider (Anthropic), one default model (claude-sonnet-4-6). Used
by `services/searcher/` for native web_search. Other services use
`shared/openai_client.py` (OpenAI) - do not cross-pollinate without an
explicit design discussion.

Exposes one method today:
- `search_web(query, ...)` - LLM-driven web search via the native
  web_search server tool. Returns the raw Messages API response;
  callers extract whatever they need.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4000
DEFAULT_MAX_USES = 5
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"


class AnthropicClient:
    """Thin Anthropic wrapper. One method per capability - keep small."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from anthropic import Anthropic  # type: ignore[reportMissingImports]

        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def search_web(
        self,
        query: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_uses: int = DEFAULT_MAX_USES,
    ) -> Any:
        """Run an LLM-driven web search via Anthropic's native web_search tool.

        Returns the raw `Message` response object. Callers extract URLs,
        titles, and cited text from `response.content` (see the searcher
        stage for the parsing pattern).
        """
        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            tools=[
                {
                    "type": WEB_SEARCH_TOOL_TYPE,
                    "name": "web_search",
                    "max_uses": max_uses,
                }
            ],
            messages=[{"role": "user", "content": query}],
        )
