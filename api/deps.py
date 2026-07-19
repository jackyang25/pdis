"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

import os
from typing import Mapping, Any

from fastapi import HTTPException

from shared.openai_client import OpenAIClient
from services.searcher import SearchRuntime


def get_openai_client() -> OpenAIClient:
    """Construct the OpenAI client using OPENAI_API_KEY from the environment."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY in server environment.")
    return OpenAIClient()


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
        integrations=dict(integrations or {}),
    )
