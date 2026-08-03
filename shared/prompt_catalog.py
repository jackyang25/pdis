"""How every tool declares the model prompts it sends, for publication.

Stage modules own their prompt text. A catalog owns nothing but the list of
prompts, how to render each one with placeholder document content, and what each
one produces. One shape for every tool, so the reference generator, the drift
test, and the documentation page need no per-tool special cases.

A published prompt is process documentation, not run provenance: it carries
placeholder slots where a document's own content is interpolated, never the
content of any particular run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CatalogEntry:
    """One prompt: which tool sends it, how to render it, and what it produces."""

    tool: str
    """Tool key, matching the workflow graph and documentation panel it belongs to."""

    id: str
    stage: str
    """Stage key. Unique within a tool, not across the suite - `tool` qualifies it."""

    title: str
    builder_name: str
    """The function in the stage module that assembles this prompt."""

    render: Callable[[], str]
    framing_slot: str | None
    """Config field interpolated into this prompt, when the tool has one."""

    result_fields: tuple[str, ...]
    ui_labels: tuple[str, ...]
    """Interface labels this prompt produces, so a tooltip can link back here."""


def catalog_reference(tool: str, stage: str) -> str:
    """The documentation anchor for one prompt.

    Qualified by tool because stage names are only unique within a tool, and two
    tools may reasonably both call a stage `grader`.
    """
    return f"prompt-{tool}-{stage}"
