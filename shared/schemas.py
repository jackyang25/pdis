"""Schema fragments every stage's structured output shares.

A parser that strips whitespace and refuses what is left empty rejects `"  "`, so a schema
that says only `minLength: 1` permits an answer its own validator refuses - an answer the
model cannot get right. The pattern closes that: at least one non-space character.
"""

from __future__ import annotations

from typing import Any


def non_empty_text(**extra: Any) -> dict[str, Any]:
    """A string that says something: non-empty after whitespace is stripped."""
    return {"type": "string", "minLength": 1, "pattern": "\\S", **extra}


def blank_text() -> dict[str, Any]:
    """A string that must be empty - a field a variant of an answer does not use."""
    return {"type": "string", "enum": [""]}
