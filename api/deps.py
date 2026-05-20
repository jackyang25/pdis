"""Shared dependencies: LLM client construction from environment."""

from __future__ import annotations

import os

from fastapi import HTTPException

from shared.llm_client import LLMClient


def get_llm_client() -> LLMClient:
    """Construct the LLM client using OPENAI_API_KEY from the environment."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY in server environment.")
    return LLMClient()
