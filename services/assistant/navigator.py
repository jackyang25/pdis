"""The results source: a compact map of every held result, then exact paths on demand.

Ask treats ANY result object (Scout, Inspector, future doc types) as a plain JSON
tree and reads it ONLY through these helpers:

  - overview(index)        -> a compact map so the agent knows what paths exist
  - get(index, path)       -> the subtree at a dotted/indexed path
  - find(index, query)     -> paths whose key or value contains the query

Nothing here knows about Scout/Inspector specifics - that semantic meaning is
supplied separately by a per-result-type legend. This keeps the assistant
decoupled: a new result type needs only a legend, no changes here.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import limits, sources
from .workspace import WorkspaceIndex

_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def overview(index: WorkspaceIndex) -> str:
    """Each held result and the draft: what it is, what it read, and its top two levels."""
    if not index.results:
        return "No results are held."
    # Walk the bundle's own list so each path is the entry's real position there; the
    # index's results are the same entries, in the same order, minus any without a type.
    raw = [
        (position, entry)
        for position, entry in enumerate(index.bundle.get("results") or [])
        if isinstance(entry, dict) and entry.get("result_type")
    ]
    finals = [entry for entry in index.results if not entry.draft]
    rows = [(f"results[{position}]", entry, raw_entry.get("analysis"))
            for (position, raw_entry), entry in zip(raw, finals)]
    if index.has_review:
        draft = next(entry for entry in index.results if entry.draft)
        rows.append(("active_review", draft, index.bundle["active_review"].get("analysis")))
    lines = []
    for path, entry, analysis in rows:
        state = "draft" if entry.draft else "final"
        reads = ", ".join(entry.doc_ids) or "no documents"
        lines.append(f"- [{entry.id}] {entry.result_type} · {entry.label} · {state} · reads: {reads} · path: {path}")
        lines.extend(f"  {line}" for line in _structure(analysis, limits.MAP_LINES_PER_RESULT))
    return "\n".join(lines)


def _structure(node: Any, cap: int) -> list[str]:
    """Field names and list sizes two levels deep, capped."""
    lines: list[str] = []

    def describe(value: Any) -> str:
        if isinstance(value, list):
            return f"list ({len(value)} items)"
        if isinstance(value, dict):
            return f"object ({len(value)} fields)"
        text = " ".join(str(value).split())
        return text if len(text) <= limits.MAP_FIELD_VALUE_CHARS else text[: limits.MAP_FIELD_VALUE_CHARS] + "…"

    if isinstance(node, dict):
        for key, value in node.items():
            lines.append(f"{key}: {describe(value)}")
            if isinstance(value, dict):
                lines.extend(f"  {child}: {describe(grand)}" for child, grand in value.items())
    total = len(lines)
    if total > cap:
        lines = lines[:cap] + [f"…[{total - cap} more fields; use find_result]"]
    return lines


def get(index: WorkspaceIndex, path: str) -> str:
    node = _traverse(index.bundle, path.strip())
    return sources.truncate(json.dumps(node, indent=2, default=str, ensure_ascii=False),
                            limits.MAX_RESULT_CHARS, "narrow the path")


def find(index: WorkspaceIndex, query: Any) -> str:
    term = sources.search_term(query)
    if term is None:
        return sources.EMPTY_QUERY
    needle, hits = term.lower(), []

    # The walk visits every node, so the overflow line counts every match rather than
    # the one that tripped the cap. Hits past the cap are only counted, never worded.
    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else key
                if needle in str(key).lower():
                    hits.append(sources.Hit(id=child, snippet=""))
                walk(value, child)
        elif isinstance(node, list):
            for position, value in enumerate(node):
                walk(value, f"{path}[{position}]")
        elif isinstance(node, str) and needle in node.lower():
            shown = len(hits) < limits.MAX_FIND_HITS
            hits.append(sources.Hit(
                id=path,
                snippet=sources.snippet(node, node.lower().find(needle), len(needle)) if shown else "",
            ))

    walk(index.bundle, "")
    return sources.render_hits(hits, limits.MAX_FIND_HITS)


def _traverse(node: Any, path: str) -> Any:
    if not path:
        return node
    for key, idx in _PATH_TOKEN.findall(path):
        if key:
            node = node.get(key) if isinstance(node, dict) else None
        elif idx != "":
            i = int(idx)
            node = node[i] if isinstance(node, list) and 0 <= i < len(node) else None
        if node is None:
            return None
    return node
