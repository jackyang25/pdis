"""Shared UI helpers for the tool suite.

Sidebar labels mirror CLI flag names 1:1. Section headers reflect actual
config concerns, not user-friendly translations.

Sidebar layout convention (top to bottom in app.py + tool sidebars):
    1. document   — org / source_type / intervention / therapeutic_area
    2. (Tool selector)
    3. mode       — single / batch (UI-only affordance)
    4. input      — file(s), source_kind, map
    5. llm        — provider / model / api_key
    6. tunables   — max_tokens / max_workers
    7. Run / Clear buttons
"""

from __future__ import annotations

import os
from typing import Callable

import streamlit as st

from llm_client import PROVIDER_ENV_VAR


PROVIDER_CHOICES = ["anthropic", "openai"]


# ---------------------------------------------------------------------------
# Layout / chrome
# ---------------------------------------------------------------------------


def render_header(title: str, subtitle: str, caption: str | None = None) -> None:
    """Page title pattern: `<Tool Name> — <Subtitle>` + one-line caption."""
    st.title(f"{title} — {subtitle}")
    if caption:
        st.caption(caption)


def render_empty_state(message: str) -> None:
    st.info(message)


def render_section(name: str) -> None:
    """Sidebar section header. Use the code-name (e.g. `llm`, `tunables`)."""
    st.sidebar.markdown(f"**{name}**")


# ---------------------------------------------------------------------------
# llm — mirrors --provider / --model / --api-key
# ---------------------------------------------------------------------------


def render_llm_controls(
    key_prefix: str,
    *,
    default_model_for_provider: Callable[[str], str],
    env_fallback: bool = True,
) -> tuple[str, str, str]:
    """Returns (provider, model, api_key). Labels match CLI flag names."""
    render_section("llm")
    provider = st.sidebar.selectbox(
        "provider",
        PROVIDER_CHOICES,
        key=f"{key_prefix}_provider",
    )
    model = st.sidebar.text_input(
        "model",
        value=default_model_for_provider(provider),
        key=f"{key_prefix}_model_{provider}",
    )
    default_api_key = (
        os.environ.get(PROVIDER_ENV_VAR[provider], "") if env_fallback else ""
    )
    api_key = st.sidebar.text_input(
        "api_key",
        value=default_api_key,
        type="password",
        key=f"{key_prefix}_{provider}_api_key",
    )
    return provider, model, api_key


# ---------------------------------------------------------------------------
# tunables — mirrors --max-tokens / --max-workers
# ---------------------------------------------------------------------------


def render_advanced_controls(
    key_prefix: str,
    *,
    default_max_tokens: int,
    show_max_workers: bool = False,
    default_max_workers: int = 4,
) -> dict:
    """Returns {max_tokens, [max_workers]}. Labels match CLI flag names."""
    render_section("tunables")
    settings: dict = {}
    settings["max_tokens"] = st.sidebar.number_input(
        "max_tokens",
        min_value=1000,
        max_value=64000,
        value=default_max_tokens,
        step=1000,
        help="CLI: --max-tokens",
        key=f"{key_prefix}_max_tokens",
    )
    if show_max_workers:
        settings["max_workers"] = st.sidebar.number_input(
            "max_workers",
            min_value=1,
            max_value=16,
            value=default_max_workers,
            step=1,
            help="CLI: --max-workers",
            key=f"{key_prefix}_max_workers",
        )
    return settings
