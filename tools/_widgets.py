"""Shared Streamlit sidebar widgets for the tool suite.

Every `tools/*_tool.py` uses these helpers so the sidebar stays symmetric
and widget outputs map cleanly to the kwargs each library's
`pipeline.run_pipeline(...)` already accepts.
"""

from __future__ import annotations

import os
from typing import Callable

import streamlit as st

from llm_client import PROVIDER_ENV_VAR


PROVIDER_CHOICES = ["anthropic", "openai"]


def render_llm_controls(
    key_prefix: str,
    *,
    default_model_for_provider: Callable[[str], str],
    env_fallback: bool = True,
) -> tuple[str, str, str]:
    """Sidebar widgets for provider / model / api_key.

    Returns (provider, model, api_key) — names match the kwargs each tool's
    `run_pipeline` expects.
    """
    provider = st.sidebar.selectbox(
        "LLM provider",
        PROVIDER_CHOICES,
        key=f"{key_prefix}_llm_provider",
    )
    model = st.sidebar.text_input(
        "Model",
        value=default_model_for_provider(provider),
        key=f"{key_prefix}_llm_model_{provider}",
    )
    api_label = "Anthropic API key" if provider == "anthropic" else "OpenAI API key"
    default_api_key = (
        os.environ.get(PROVIDER_ENV_VAR[provider], "") if env_fallback else ""
    )
    api_key = st.sidebar.text_input(
        api_label,
        value=default_api_key,
        type="password",
        key=f"{key_prefix}_{provider}_api_key",
    )
    return provider, model, api_key


def render_advanced_controls(
    key_prefix: str,
    *,
    default_max_tokens: int,
    show_max_workers: bool = False,
    default_max_workers: int = 4,
) -> dict:
    """Sidebar expander mirroring CLI knobs (max_tokens, optional max_workers).

    Returns a dict with the same keys as the CLI flags' destination names so
    callers can `run_pipeline(..., **advanced)`.
    """
    settings: dict = {}
    with st.sidebar.expander("Advanced", expanded=False):
        settings["max_tokens"] = st.number_input(
            "Max output tokens",
            min_value=1000,
            max_value=64000,
            value=default_max_tokens,
            step=1000,
            help="Max tokens the LLM can return per call. CLI: --max-tokens.",
            key=f"{key_prefix}_max_tokens",
        )
        if show_max_workers:
            settings["max_workers"] = st.number_input(
                "Max workers",
                min_value=1,
                max_value=16,
                value=default_max_workers,
                step=1,
                help="Documents processed in parallel. CLI: --max-workers.",
                key=f"{key_prefix}_max_workers",
            )
    return settings
