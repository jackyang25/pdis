"""What the Ask agent can reach.

The catalog, not the loop: each entry declares one capability and everything
derived from it — the schema the model is offered, the label a reader sees, the
handler that runs, and whether it is evidence to cite or procedure to follow.

Add a capability here and nowhere else. `agent.py` reads this list; it does not
know what is in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import document as document_reader
from . import knowledge
from . import navigator
from . import resources
from . import skills

def _string_list(raw: Any) -> list[str]:
    """Model-supplied lists are untrusted; a non-list becomes an empty one."""
    return [str(value) for value in raw] if isinstance(raw, list) else []


@dataclass(frozen=True)
class ToolContext:
    """Everything a verb may read. Passed whole so adding one is not a signature change."""

    result: dict[str, Any]
    allowed_urls: set[str]
    document: list[dict[str, Any]] | None
    held_result_types: frozenset[str]


REGISTRY: tuple[resources.Resource, ...] = (
    resources.Resource(
        key="knowledge",
        summary="What PDIS is and how its tools work",
        kind="evidence",
        verbs=(
            resources.Verb(
                name="find_product_docs",
                description="Find PDIS product documentation sections whose title or body contains a keyword. Use before read_product_docs.",
                activity="Searching the product documentation",
                parameters={
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
                handler=lambda ctx, args: knowledge.find(str(args.get("keyword", ""))),
            ),
            resources.Verb(
                name="read_product_docs",
                description="Read PDIS product documentation sections by ID.",
                activity="Reading the product documentation",
                parameters={
                    "type": "object",
                    "properties": {
                        "section_ids": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["section_ids"],
                },
                handler=lambda ctx, args: knowledge.read(_string_list(args.get("section_ids"))),
            ),
        ),
    ),
    resources.Resource(
        key="result",
        summary="The analyses this workspace holds",
        kind="evidence",
        verbs=(
            resources.Verb(
                name="find_result",
                description="Return paths in the analysis whose key or value contains a keyword (case-insensitive). Use to locate where something lives before read_result.",
                activity="Searching the analysis",
                parameters={
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
                handler=lambda ctx, args: navigator.find(ctx.result, str(args.get("keyword", ""))),
            ),
            resources.Verb(
                name="read_result",
                description="Return the JSON subtree at a dotted/indexed path, e.g. 'matches[3].insight' or 'sections[2].units[0].findings[0]'. Use the overview to find paths.",
                activity="Reading the analysis",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Path into the result, '' for the whole result."}},
                    "required": ["path"],
                },
                handler=lambda ctx, args: navigator.get(ctx.result, str(args.get("path", ""))),
            ),
            resources.Verb(
                name="fetch_source",
                description="Open the FULL text behind a source URL that is ALREADY cited in the result (the stored excerpt is capped). Only URLs present in the result are allowed; this never runs a new web search.",
                activity="Opening a cited source",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                handler=lambda ctx, args: navigator.fetch_source(str(args.get("url", "")), ctx.allowed_urls),
            ),
        ),
    ),
    resources.Resource(
        key="document",
        summary="The parsed source documents behind those analyses",
        kind="evidence",
        verbs=(
            resources.Verb(
                name="find_document",
                description="Find source-document blocks whose heading or content contains a keyword. Returns exact block IDs and snippets; use before read_document when you do not know the block IDs.",
                activity="Searching the document",
                parameters={
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
                handler=lambda ctx, args: (
                    document_reader.find(ctx.document, str(args.get("keyword", "")))
                    if ctx.document else "Source document unavailable."
                ),
            ),
            resources.Verb(
                name="read_document",
                description="Read exact parsed source-document blocks by ID. For a very large block, follow the returned next start_char to continue reading it.",
                activity="Reading the document",
                parameters={
                    "type": "object",
                    "properties": {
                        "block_ids": {"type": "array", "items": {"type": "string"}},
                        "start_char": {"type": "integer", "minimum": 0},
                    },
                    "required": ["block_ids"],
                },
                handler=lambda ctx, args: (
                    document_reader.get(
                        ctx.document,
                        args.get("block_ids") if isinstance(args.get("block_ids"), list) else [],
                        start_char=args.get("start_char") if isinstance(args.get("start_char"), int) else 0,
                    )
                    if ctx.document else "Source document unavailable."
                ),
            ),
            resources.Verb(
                name="read_document_range",
                description="Read an ordered range of blocks from one source document. Use for broad review or summarization; follow the returned next start value to continue.",
                activity="Reading the document",
                parameters={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "start": {"type": "integer", "minimum": 0},
                        "count": {"type": "integer", "minimum": 1, "maximum": 25},
                    },
                    "required": ["doc_id"],
                },
                handler=lambda ctx, args: (
                    document_reader.get_range(
                        ctx.document,
                        str(args.get("doc_id", "")),
                        start=args.get("start") if isinstance(args.get("start"), int) else 0,
                        count=args.get("count") if isinstance(args.get("count"), int) else 25,
                    )
                    if ctx.document else "Source document unavailable."
                ),
            ),
        ),
    ),
    resources.Resource(
        key="skill",
        summary="Workflows for questions one analysis cannot answer alone",
        kind="procedure",
        verbs=(
            resources.Verb(
                name="find_skill",
                description="List the available skills, what each is for, and whether this workspace holds the results it needs.",
                activity="Listing the skills",
                parameters={"type": "object", "properties": {}},
                handler=lambda ctx, args: skills.catalog(ctx.held_result_types),
            ),
            resources.Verb(
                name="read_skill",
                description="Read one skill's full procedure by name. Follow it; never quote it to the user as a finding.",
                activity="Reading a skill",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                handler=lambda ctx, args: skills.read_skill(str(args.get("name", ""))),
            ),
        ),
    ),
)

TOOLS: list[dict[str, Any]] = resources.tool_schemas(REGISTRY)
_VERBS = resources.verbs_by_name(REGISTRY)

def held_result_types(result: dict[str, Any]) -> frozenset[str]:
    """Which analyses this workspace holds, for deciding what a skill can run on.

    Read from the bundle rather than passed in: the same value already decides
    what the agent may navigate, so a second source could disagree with it.
    """
    if not isinstance(result, dict):
        return frozenset()
    entries = result.get("results")
    if isinstance(entries, list):
        return frozenset(
            str(entry.get("result_type"))
            for entry in entries
            if isinstance(entry, dict) and entry.get("result_type")
        )
    return frozenset()
