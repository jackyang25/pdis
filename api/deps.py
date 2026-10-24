"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Mapping
from urllib.parse import urlparse

from shared.anthropic_client import AnthropicQuantitativeClient
from shared.openai_client import OpenAIClient
from services.searcher import (
    TAVILY_INTEGRATION,
    SearchRuntime,
    TavilyHTTPConnector,
    ToolUniverseHTTPConnector,
    integration_operations,
)

TOOLUNIVERSE_INTEGRATION = "tooluniverse"


class ConfigurationError(RuntimeError):
    """A configuration value is present but cannot be read as what it must be.

    Distinct from `MissingCredentialError`: an absent credential is a deployment
    that has not finished, and is reported to the caller that needs it, whereas
    an unparseable number is a typo that will never resolve itself. Raising it
    keeps a malformed value from being silently replaced by a default that
    happens to work, which is how a tuning change appears to take effect and
    does not.
    """


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
    if not (os.environ.get("KONG_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise MissingCredentialError("Missing KONG_KEY or OPENAI_API_KEY in server environment.")
    return _openai_client()


def get_quantitative_anthropic_client() -> AnthropicQuantitativeClient:
    """Return Scout's server-owned Opus quantitative mapping client, one per process."""
    if not (os.environ.get("KONG_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
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
        # Unset options keep the connector's own defaults: its endpoint, and advanced
        # depth, because the reason to run this lane is the quality of the extracted
        # page text. Depth is overridable for a cheaper comparison run.
        options = {
            name: value
            for name, value in (
                ("base_url", os.environ.get("TAVILY_BASE_URL", "").strip()),
                ("search_depth", os.environ.get("TAVILY_SEARCH_DEPTH", "").strip()),
            )
            if value
        }
        configured[TAVILY_INTEGRATION] = TavilyHTTPConnector(
            api_key=api_key,
            timeout_seconds=_positive_float("TAVILY_TIMEOUT_SECONDS", 30.0),
            **options,
        )
    configured.update(overrides or {})
    return configured


def _tooluniverse_base_url() -> str:
    """Resolve the connector's address, or empty when no connector is configured.

    One variable, because one is enough: a host and port pair says nothing a URL
    cannot, and two ways to state an address means a deployment can set both and
    be wrong in a way neither value reveals. Platforms that publish a private
    service as host and port compose them in the deployment manifest - see the
    `template` block in `jobspec.nomad`, which resolves the connector through
    service discovery and writes this variable.

    Unset means no connector, which retrieval already handles by disabling that
    lane. Set but naming no host is a misconfiguration, and is refused rather
    than treated as either - the same rule `validate_configuration` applies to
    every other setting, for the same reason: a value someone meant to set and
    got wrong should say so, not disappear into a default.
    """
    configured = os.environ.get("TOOLUNIVERSE_BASE_URL", "").strip()
    if configured and not urlparse(configured).netloc:
        raise ConfigurationError(
            f"TOOLUNIVERSE_BASE_URL must be an absolute URL, got {configured!r}"
        )
    return configured


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(
            f"{name} must be a positive integer, got {raw!r}"
        ) from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer, got {value}")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(
            f"{name} must be a positive number, got {raw!r}"
        ) from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive number, got {value}")
    return value


# Every numeric setting the gateway reads, with the default that applies when it
# is unset. `validate_configuration()` parses all of them at import time so a
# typo stops the process at boot with the variable's name, rather than surfacing
# later as a default that quietly replaced the value someone meant to set.
NUMERIC_SETTINGS: tuple[tuple[str, int | float], ...] = (
    ("SEARCH_GLOBAL_WORKER_LIMIT", 48),
    ("TOOLUNIVERSE_TIMEOUT_SECONDS", 30.0),
    ("TAVILY_TIMEOUT_SECONDS", 30.0),
    ("MAX_CONCURRENT_RUNS", 2),
)


def validate_configuration() -> None:
    """Parse every numeric setting once, at startup.

    Credentials are deliberately not checked here. Their absence is reported to
    the request that needs one, for the reason `MissingCredentialError` records:
    these constructors run inside streaming workers. Parsing has no such
    constraint, so it happens as early as it can.
    """
    for name, default in NUMERIC_SETTINGS:
        if isinstance(default, int):
            _positive_int(name, default)
        else:
            _positive_float(name, default)
    _tooluniverse_base_url()
