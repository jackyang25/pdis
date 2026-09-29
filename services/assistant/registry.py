"""What the Ask agent can reach.

The catalog, not the loop: each entry declares one capability and everything
derived from it — the schema the model is offered, the label a reader sees, the
handler that runs, and whether it is evidence to cite or procedure to follow.

Add a capability here and nowhere else. `agent.py` reads this list; it does not
know what is in it.

Every handler reads one `WorkspaceIndex` — the request's whole reachable world,
built once by `workspace.build_index` — rather than a scatter of separate
result/document/allowed-url arguments. `run_tool` is the one dispatcher: it
parses a model tool call, routes it to the verb that declared it, and always
hands back a provider-neutral `ToolOutput`, whether the handler itself returned
plain text or an image-bearing `ToolOutput`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from shared.chat import ToolCall, ToolOutput

from . import document as document_reader
from . import knowledge
from . import limits
from . import navigator
from . import resources
from . import skills
from . import web_sources
from .document import VisualBudget
from .workspace import WorkspaceIndex


def _string_list(raw: Any) -> list[str]:
    """Model-supplied lists are untrusted; a non-list becomes an empty one."""
    return [str(value) for value in raw] if isinstance(raw, list) else []


def _int(raw: Any, default: int) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else default


@dataclass(frozen=True)
class ToolContext:
    """Everything a verb may read, and the question's visual budget."""

    index: WorkspaceIndex
    budget: VisualBudget


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
                handler=lambda ctx, args: knowledge.find(args.get("keyword")),
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
        summary="The workspace catalog, final analyses and any active review draft",
        kind="evidence",
        verbs=(
            resources.Verb(
                name="find_result",
                description="Return paths in the submitted workspace whose key or value contains a keyword (case-insensitive), including any active_review. Use to locate where something lives before read_result.",
                activity="Searching the analysis",
                parameters={
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
                handler=lambda ctx, args: navigator.find(ctx.index, args.get("keyword")),
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
                handler=lambda ctx, args: navigator.get(ctx.index, str(args.get("path", ""))),
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
                handler=lambda ctx, args: web_sources.fetch_source(
                    str(args.get("url", "")), set(ctx.index.allowed_urls)
                ),
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
                description=(
                    "Find source-document blocks whose heading or content contains a keyword. "
                    "Returns exact block IDs and snippets; use before read_document when you do "
                    "not know the block IDs. When matches exceed the cap, the result says how "
                    "many more each document holds; pass doc_id to search one."
                ),
                activity="Searching the document",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "doc_id": {
                            "type": "string",
                            "description": "Search only this document, by the doc_id the map shows.",
                        },
                    },
                    "required": ["keyword"],
                },
                handler=lambda ctx, args: document_reader.find(
                    ctx.index,
                    args.get("keyword"),
                    doc_id=str(args["doc_id"]) if args.get("doc_id") else None,
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
                handler=lambda ctx, args: document_reader.get(
                    ctx.index,
                    _string_list(args.get("block_ids")),
                    start_char=_int(args.get("start_char"), 0),
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
                        "count": {"type": "integer", "minimum": 1, "maximum": limits.MAX_RANGE_BLOCKS},
                    },
                    "required": ["doc_id"],
                },
                handler=lambda ctx, args: document_reader.get_range(
                    ctx.index,
                    str(args.get("doc_id", "")),
                    start=_int(args.get("start"), 0),
                    count=_int(args.get("count"), limits.MAX_RANGE_BLOCKS),
                ),
            ),
            resources.Verb(
                name="view_document_visuals",
                description=(
                    "Look at the retained images of document blocks by exact block ID: slides, "
                    "pages, figures. Returns each image labelled with its exact block ID, its "
                    "location, and the IDs of the text on the same slide or page to read with "
                    f"read_document. At most {limits.MAX_VISUALS_PER_CALL} per call and "
                    f"{limits.MAX_VISUALS_PER_QUESTION} per question: choose blocks from the map's "
                    "visual locations or find_document, and say which ones you viewed."
                ),
                activity="Looking at the document visuals",
                parameters={
                    "type": "object",
                    "properties": {"block_ids": {"type": "array", "items": {"type": "string"},
                                                 "maxItems": limits.MAX_VISUALS_PER_CALL}},
                    "required": ["block_ids"],
                },
                handler=lambda ctx, args: document_reader.view(
                    ctx.index, _string_list(args.get("block_ids")), ctx.budget),
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
                handler=lambda ctx, args: skills.catalog(ctx.index.held_result_types),
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
VERBS = resources.verbs_by_name(REGISTRY)


def run_tool(call: ToolCall, context: ToolContext) -> ToolOutput:
    """Route one model tool call to the verb that declared it."""
    verb = VERBS.get(call.name)
    if verb is None:
        return ToolOutput(f"Unknown tool: {call.name}")
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return ToolOutput("Invalid tool arguments.")
    if not isinstance(args, dict):
        return ToolOutput("Invalid tool arguments.")
    output = verb.handler(context, args)
    return output if isinstance(output, ToolOutput) else ToolOutput(str(output))
