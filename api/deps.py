"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from shared import settings
from shared.anthropic_client import AnthropicQuantitativeClient
from shared.openai_client import OpenAIClient
from services.searcher import (
    TAVILY_INTEGRATION,
    SearchRuntime,
    TavilyHTTPConnector,
)


class MissingCredentialError(RuntimeError):
    """A required provider credential is absent from the server environment.

    A domain error rather than an ``HTTPException``: these constructors run inside
    streaming workers, where raising a transport error would be caught by the
    streaming machinery and reported as an event on an already-successful
    response. Routes map this to a status code where they still can.
    """


def get_openai_client() -> OpenAIClient:
    """Return the process's client and its server-owned two-tier model policy.

    One per process, not one per request: the client holds nothing per call, its
    credentials come from the server environment, and the SDK client it wraps
    keeps a connection pool that a fresh instance per request would discard.
    """
    if not (settings.text("KONG_KEY") or settings.text("OPENAI_API_KEY")):
        raise MissingCredentialError("Missing KONG_KEY or OPENAI_API_KEY in server environment.")
    return _openai_client()


def get_quantitative_anthropic_client() -> AnthropicQuantitativeClient:
    """Return Scout's server-owned Opus quantitative mapping client, one per process."""
    if not (settings.text("KONG_KEY") or settings.text("ANTHROPIC_API_KEY")):
        raise MissingCredentialError(
            "Missing KONG_KEY or ANTHROPIC_API_KEY in server environment."
        )
    return _anthropic_client()


@lru_cache(maxsize=1)
def _openai_client() -> OpenAIClient:
    return OpenAIClient()


@lru_cache(maxsize=1)
def _anthropic_client() -> AnthropicQuantitativeClient:
    return AnthropicQuantitativeClient()


def get_search_runtime(
    llm_client: OpenAIClient | None = None,
    *,
    integrations: Mapping[str, Any] | None = None,
) -> SearchRuntime:
    """Compose retrieval capabilities at the application boundary.

    Source adapters consume this generic runtime. Adding a connector or a provider
    key extends ``get_search_integrations`` or ``get_search_credentials`` here rather
    than changing Scout or its stages.
    """
    return SearchRuntime(
        llm_client=llm_client or get_openai_client(),
        credentials=get_search_credentials(),
        integrations=get_search_integrations(integrations),
        contact_email=settings.text("SEARCH_CONTACT_EMAIL"),
    )


def get_search_credentials() -> dict[str, str]:
    """The provider keys this deployment configured, by the provider's rate group.

    Each raises that provider's quota. Semantic Scholar does not answer in practice
    without its key, so its lane reports itself unconfigured until one is set.
    """
    keys = {
        "ncbi": settings.text("NCBI_API_KEY"),
        "openfda": settings.text("OPENFDA_API_KEY"),
        "semantic_scholar": settings.text("SEMANTIC_SCHOLAR_API_KEY"),
    }
    return {provider: value for provider, value in keys.items() if value}


def get_search_integrations(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build optional connector capabilities without exposing credentials."""
    configured: dict[str, Any] = {}
    if api_key := settings.text("TAVILY_API_KEY"):
        configured[TAVILY_INTEGRATION] = TavilyHTTPConnector(api_key=api_key)
    configured.update(overrides or {})
    return configured


def validate_configuration() -> None:
    """Parse every typed setting once, at startup.

    Credentials are deliberately not checked here. Their absence is reported to the request
    that needs one, for the reason `MissingCredentialError` records: these constructors run
    inside streaming workers. Parsing has no such constraint, so it happens as early as it
    can.
    """
    settings.validate()
