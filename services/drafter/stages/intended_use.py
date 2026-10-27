"""How a stated intended use is put to a model, in one form for every stage that reads it."""

from __future__ import annotations


def intended_use_line(intended_use: str) -> str:
    """The team's own words, labelled as theirs, or nothing when they stated none."""
    return f"Intended use, as the team drafting this profile stated it: {intended_use}\n" if intended_use else ""
