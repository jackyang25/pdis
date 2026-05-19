"""Shared dependencies: LLM client construction from environment."""

from __future__ import annotations

import os
from fastapi import HTTPException

from llm_client import (
    PROVIDER_ENV_VAR,
    LLMClient,
    create_llm_client,
    default_model_for_provider,
)

DEFAULT_PROVIDER = os.environ.get("PDIS_DEFAULT_PROVIDER", "openai")


def get_llm_client(provider: str | None = None, model: str | None = None) -> LLMClient:
    """Construct an LLM client using server-side API keys from env."""
    provider = (provider or DEFAULT_PROVIDER).lower()
    env_var = PROVIDER_ENV_VAR.get(provider)
    if env_var is None:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=f"Missing {env_var} in server environment.",
        )
    return create_llm_client(provider, api_key, model or default_model_for_provider(provider))
