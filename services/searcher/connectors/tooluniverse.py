"""Minimal, allowlisted client for ToolUniverse's official HTTP API.

The full ToolUniverse SDK intentionally contains a broad scientific/agent
runtime. PDIS keeps that deployment separate and injects this small transport
client into Searcher. Source adapters still own query grammar and response
normalization; this connector only executes an explicitly allowed tool.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from ..errors import RetrievalError
from .. import transport
from ..transport import MAX_ATTEMPTS, fetch_json

#: A wrapped provider's rate limit, as ToolUniverse reports it. The server answers 200 and
#: carries the provider's refusal as text ("Semantic Scholar API error 429"), so the
#: transport, which retries on HTTP status, never saw it as a rate limit: one live run lost
#: 47 Semantic Scholar requests this way. Classifying the failure's kind from the provider's
#: own message is error handling, not reading meaning out of content.
_RATE_LIMIT = re.compile(r"\b429\b|rate.?limit|too many requests", re.IGNORECASE)
#: Ceiling on time spent waiting out one tool's rate limit, so a throttled lane cannot hold
#: a worker for longer than the transport's own deadline.
RATE_LIMIT_DEADLINE_SECONDS = 60.0


@dataclass(frozen=True)
class ToolUniverseHTTPConnector:
    """Execute an allowlisted ToolUniverse tool over its HTTP API."""

    base_url: str
    # Kept out of repr, so a logged or failing connector never prints its credential.
    api_token: str = field(default="", repr=False)
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ToolUniverse base URL must be an absolute HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("ToolUniverse timeout must be positive")

    def run(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        """Run one approved tool and return its JSON-compatible result.

        Raises `RetrievalError` with the server's or the tool's own message. `use_cache`
        stays off: reuse within a run is Searcher's (`SearchRuntime.calls`), whose
        lifetime is the run, while the server's cache would outlive it unseen.
        """
        if tool_name not in self.allowed_tools:
            raise ValueError(f"ToolUniverse tool is not allowlisted: {tool_name}")
        deadline = time.monotonic() + RATE_LIMIT_DEADLINE_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._run_once(tool_name, arguments)
            except RetrievalError as exc:
                delay = transport.backoff_delay(attempt)
                if exc.code != "rate_limited" or attempt == MAX_ATTEMPTS or time.monotonic() + delay >= deadline:
                    raise
                transport.pause(delay)
        raise AssertionError("unreachable")

    def _run_once(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        payload = {
            "method": "run_one_function",
            "kwargs": {
                "function_call_json": {
                    "name": tool_name,
                    "arguments": dict(arguments),
                },
                "use_cache": False,
                "validate": True,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        provider = f"ToolUniverse {tool_name}"
        body = fetch_json(
            f"{self.base_url.rstrip('/')}/api/call",
            provider=provider,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
            timeout=self.timeout_seconds,
            secrets=(self.api_token,),
        )
        if not isinstance(body, dict) or not body.get("success"):
            message = (
                str(body.get("error") or "unknown ToolUniverse error")
                if isinstance(body, dict)
                else "invalid response"
            )
            raise _tool_failure(provider, message)
        result = body.get("result")
        if isinstance(result, dict) and result.get("status") == "error":
            raise _tool_failure(provider, str(result.get("error") or "unknown error"))
        return result


def _tool_failure(provider: str, message: str) -> RetrievalError:
    if _RATE_LIMIT.search(message):
        return RetrievalError(provider, "rate_limited", message, status=429)
    return RetrievalError(provider, "tool_error", message)
