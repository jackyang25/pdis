"""Generic, result-agnostic navigation over a JSON result tree.

The Ask assistant treats ANY result object (Scout, Reviewer, future doc types)
as a plain JSON tree and reads it ONLY through these helpers:

  - overview(result)        -> a compact map so the agent knows what paths exist
  - get(result, path)       -> the subtree at a dotted/indexed path
  - find(result, keyword)   -> paths whose key or value contains the keyword
  - fetch_source(url, ...)  -> full text behind an ALREADY-CITED url (no new search)

Nothing here knows about Scout/Reviewer specifics - that semantic meaning is
supplied separately by a per-result-type legend. This keeps the assistant
decoupled: a new result type needs only a legend, no changes here.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

MAX_GET_CHARS = 12000
MAX_FIND_HITS = 40
MAX_FETCH_CHARS = 20000
FETCH_TIMEOUT_SECONDS = 20

# Identifying fields used to label list items in the overview.
_LABEL_KEYS = ("name", "attribute_ref", "section_name", "variable_name", "title", "url")
_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def overview(result: Any, max_labels: int = 8) -> str:
    """A compact structural map: scalar fields, list sizes, and sample labels."""
    lines: list[str] = []

    def label(item: Any) -> str | None:
        if isinstance(item, dict):
            for key in _LABEL_KEYS:
                if item.get(key):
                    return str(item[key])
        return None

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            lines.append(f"{path}: list ({len(node)} items)")
            labels = [label(x) for x in node[:max_labels]]
            labels = [x for x in labels if x]
            if labels:
                more = " ..." if len(node) > max_labels else ""
                lines.append(f"  e.g. {', '.join(labels)}{more}")
        else:
            value = str(node)
            if len(value) > 80:
                value = value[:80] + "..."
            lines.append(f"{path}: {value}")

    walk(result, "")
    return "\n".join(lines)


def get(result: Any, path: str) -> str:
    """Return the JSON subtree at `path` (e.g. 'matches[3].insight.statement')."""
    node = _traverse(result, path.strip())
    text = json.dumps(node, indent=2, default=str, ensure_ascii=False)
    if len(text) > MAX_GET_CHARS:
        text = text[:MAX_GET_CHARS] + "\n...[truncated - narrow the path]"
    return text


def find(result: Any, keyword: str) -> str:
    """Return paths whose key or scalar value contains `keyword` (case-insensitive)."""
    needle = keyword.strip().lower()
    if not needle:
        return "(empty keyword)"
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if len(hits) >= MAX_FIND_HITS:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else key
                if needle in key.lower():
                    hits.append(child)
                walk(value, child)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")
        elif isinstance(node, str) and needle in node.lower():
            hits.append(path)

    walk(result, "")
    return "\n".join(hits[:MAX_FIND_HITS]) if hits else "(no matches)"


def collect_urls(result: Any) -> set[str]:
    """Every http(s) URL anywhere in the result - the allowlist for fetch_source."""
    urls: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.startswith(("http://", "https://")):
            urls.add(node)

    walk(result)
    return urls


def fetch_source(url: str, allowed_urls: set[str]) -> str:
    """Fetch the full text behind an ALREADY-CITED url. Grounding + safety: only
    URLs present in the result may be fetched (no fresh/arbitrary browsing)."""
    url = url.strip()
    if url not in allowed_urls:
        return (
            "Refused: that URL is not one of the sources cited in this result. "
            "I can only open links that already appear in the results."
        )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pdis-ask/0.1"})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(2_000_000).decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return f"Could not open this source ({exc}). Fall back to the excerpt in the result."

    text = _strip_html(raw)
    if len(text) > MAX_FETCH_CHARS:
        text = text[:MAX_FETCH_CHARS] + "\n...[truncated]"
    return text or "(the source returned no readable text)"


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


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
