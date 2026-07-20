"""Minimal, allowlisted client for ToolUniverse's official HTTP API.

The full ToolUniverse SDK intentionally contains a broad scientific/agent
runtime. PDIS keeps that deployment separate and injects this small transport
client into Searcher. Source adapters still own query grammar and response
normalization; this connector only executes an explicitly allowed tool.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ToolUniverseHTTPConnector:
    """Execute an allowlisted ToolUniverse tool over its HTTP API."""

    base_url: str
    api_token: str = ""
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ToolUniverse base URL must be an absolute HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("ToolUniverse timeout must be positive")

    def run(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        """Run one approved tool and return its JSON-compatible result."""
        if tool_name not in self.allowed_tools:
            raise ValueError(f"ToolUniverse tool is not allowlisted: {tool_name}")
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
        request = Request(
            f"{self.base_url.rstrip('/')}/api/call",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"ToolUniverse HTTP {exc.code} while running {tool_name}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"ToolUniverse is unavailable: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("ToolUniverse returned invalid JSON") from exc

        if not isinstance(body, dict) or not body.get("success"):
            message = (
                body.get("error", "unknown ToolUniverse error")
                if isinstance(body, dict)
                else "invalid response"
            )
            raise RuntimeError(f"ToolUniverse failed {tool_name}: {message}")
        result = body.get("result")
        if isinstance(result, dict) and result.get("status") == "error":
            error = result.get("error", "unknown error")
            raise RuntimeError(f"ToolUniverse tool failed {tool_name}: {error}")
        return result
