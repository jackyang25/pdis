"""Shared dependencies: provider client construction from environment."""

from __future__ import annotations

import os

from fastapi import HTTPException

from shared.openai_client import OpenAIClient


def get_openai_client() -> OpenAIClient:
    """Construct the OpenAI client using OPENAI_API_KEY from the environment."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY in server environment.")
    return OpenAIClient()
