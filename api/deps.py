"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

import os
from typing import Any, Mapping

from fastapi import HTTPException

from shared.anthropic_client import AnthropicReviewClient
from shared.openai_client import OpenAIClient
from services.searcher import (
    SearchRuntime,
    ToolUniverseHTTPConnector,
    integration_operations,
)

TOOLUNIVERSE_INTEGRATION = "tooluniverse"


def get_openai_client() -> OpenAIClient:
    """Construct the shared client and its server-owned two-tier model policy."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Missing OPENAI_API_KEY in server environment.",
        )
    return OpenAIClient()


def get_target_review_client() -> AnthropicReviewClient | None:
    """Build the optional, provider-diverse Scout target verifier.

    A missing Anthropic credential does not route review back through OpenAI;
    Scout instead leaves every proposal flagged for explicit human review.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return AnthropicReviewClient()


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
