"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

import os
from typing import Any, Mapping

from shared.anthropic_client import AnthropicQuantitativeClient
from shared.openai_client import OpenAIClient
from services.searcher import (
    SearchRuntime,
    TavilyHTTPConnector,
    ToolUniverseHTTPConnector,
    integration_operations,
)
from services.searcher.connectors.tavily import DEFAULT_BASE_URL, DEFAULT_SEARCH_DEPTH
from services.searcher.sources.tavily import TAVILY_INTEGRATION

TOOLUNIVERSE_INTEGRATION = "tooluniverse"


class MissingCredentialError(RuntimeError):
    """A required provider credential is absent from the server environment.

    A domain error rather than an ``HTTPException``: these constructors run inside
    streaming workers, where raising a transport error would be caught by the
    streaming machinery and reported as an event on an already-successful
    response. Routes map this to a status code where they still can.
    """


def get_openai_client() -> OpenAIClient:
    """Construct the shared client and its server-owned two-tier model policy."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise MissingCredentialError("Missing OPENAI_API_KEY in server environment.")
    return OpenAIClient()


def get_quantitative_anthropic_client() -> AnthropicQuantitativeClient:
    """Build Scout's server-owned Opus quantitative mapping client."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingCredentialError("Missing ANTHROPIC_API_KEY in server environment.")
    return AnthropicQuantitativeClient()


def get_search_runtime(
    llm_client: OpenAIClient | None = None,
    *,
    integrations: Mapping[str, Any] | None = None,
) -> SearchRuntime:
    """Compose retrieval capabilities at the application boundary.

    Source adapters consume this generic runtime. Adding a connector should
    extend ``integrations`` here rather than changing Scout or its stages.
    """
    return SearchRuntime(
        llm_client=llm_client or get_openai_client(),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        integrations=get_search_integrations(integrations),
        global_worker_limit=_positive_int("SEARCH_GLOBAL_WORKER_LIMIT", 48),
    )


def get_search_integrations(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build optional connector capabilities without exposing credentials."""
    configured: dict[str, Any] = {}
    if base_url := _tooluniverse_base_url():
        configured[TOOLUNIVERSE_INTEGRATION] = ToolUniverseHTTPConnector(
            base_url=base_url,
            api_token=os.environ.get("TOOLUNIVERSE_API_TOKEN", ""),
            allowed_tools=frozenset(integration_operations(TOOLUNIVERSE_INTEGRATION)),
            timeout_seconds=_positive_float("TOOLUNIVERSE_TIMEOUT_SECONDS", 30.0),
        )
    if api_key := os.environ.get("TAVILY_API_KEY", "").strip():
        configured[TAVILY_INTEGRATION] = TavilyHTTPConnector(
            api_key=api_key,
            base_url=os.environ.get("TAVILY_BASE_URL", "").strip() or DEFAULT_BASE_URL,
            # Advanced by default: the reason to run this lane is the quality of the
            # extracted page text, and basic depth returns less of it. Overridable for a
            # cheaper comparison run.
            search_depth=os.environ.get("TAVILY_SEARCH_DEPTH", "").strip()
            or DEFAULT_SEARCH_DEPTH,
            timeout_seconds=_positive_float("TAVILY_TIMEOUT_SECONDS", 30.0),
        )
    configured.update(overrides or {})
    return configured


def _tooluniverse_base_url() -> str:
    """Resolve an explicit URL or Render-injected private service address."""
    if explicit := os.environ.get("TOOLUNIVERSE_BASE_URL", "").strip():
        return explicit
    host = os.environ.get("TOOLUNIVERSE_HOST", "").strip()
    if not host:
        return ""
    port = os.environ.get("TOOLUNIVERSE_PORT", "8080").strip() or "8080"
    return f"http://{host}:{port}"


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default
