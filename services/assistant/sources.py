"""What every reachable kind of content shares: how it is found, shown and cut short.

Four sources are reachable - results, documents, product documentation and skills -
and each offers the same three acts: its lines in the map, a find that returns exact
identifiers (paths, block IDs, section IDs, skill names), and a read by those
identifiers. Their inputs differ, because what they read does:

  - results (`navigator`) and documents (`document`) read the request's
    `WorkspaceIndex`, since both exist only in the workspace the client submitted;
  - product documentation (`knowledge`) and skills (`skills`) are process-wide and
    read their own files, since neither changes with what a workspace holds (skills
    are only told which result types are held, to say which are ready).

What all four share is wording: the helpers below are the only place a hit, a
snippet, a truncation or an absence is phrased - and a cited web source's truncation
too - so the model meets one convention whichever source it reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import limits

EMPTY_QUERY = "(empty search term)"
NO_MATCHES = "(no matches)"


@dataclass(frozen=True)
class Hit:
    id: str
    snippet: str
    label: str = ""
    note: str = ""


def search_term(raw: Any) -> str | None:
    """A usable search term, or None when there is nothing to search for."""
    term = str(raw).strip() if raw is not None else ""
    return term or None


def snippet(text: str, index: int, length: int) -> str:
    """The text around a match, whitespace collapsed, with elisions marked."""
    begin = max(0, index - limits.SNIPPET_BEFORE)
    end = min(len(text), index + length + limits.SNIPPET_AFTER)
    body = " ".join(text[begin:end].split())
    return f"{'…' if begin else ''}{body}{'…' if end < len(text) else ''}"


def render_hits(hits: list[Hit], cap: int, overflow: str | None = None) -> str:
    if not hits:
        return NO_MATCHES
    lines = []
    for hit in hits[:cap]:
        line = f"- [{hit.id}]" + (f" {hit.label}" if hit.label else "")
        if hit.snippet:
            line += f": {hit.snippet}"
        if hit.note:
            line += f" ({hit.note})"
        lines.append(line)
    if len(hits) > cap:
        lines.append(overflow or f"…[{len(hits) - cap} more matches; search a narrower term]")
    return "\n".join(lines)


def truncate(text: str, limit: int, hint: str) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n…[truncated; {hint}]"


def unavailable(what: str) -> str:
    return f"({what} is not available in this workspace)"
