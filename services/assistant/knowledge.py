"""Read-only navigation over the canonical public PDIS documentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_KNOWLEDGE_FILE = (
    Path(__file__).resolve().parents[2] / "shared" / "product_knowledge.json"
)
MAX_FIND_HITS = 12
MAX_READ_CHARS = 16000


def load() -> dict[str, Any]:
    """Load and minimally validate the versioned documentation contract."""
    with _KNOWLEDGE_FILE.open(encoding="utf-8") as handle:
        knowledge = json.load(handle)
    if knowledge.get("version") != 1:
        raise ValueError("Unsupported product knowledge version")
    sections = knowledge.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Product knowledge must contain sections")
    section_ids = [section.get("id") for section in sections if isinstance(section, dict)]
    if any(not isinstance(section_id, str) or not section_id for section_id in section_ids):
        raise ValueError("Every product knowledge section requires an ID")
    if len(section_ids) != len(sections) or len(section_ids) != len(set(section_ids)):
        raise ValueError("Product knowledge section IDs must be unique")
    return knowledge


def overview() -> str:
    """Return a compact section map for the Assistant system prompt."""
    knowledge = load()
    lines = [
        f"{knowledge['title']} documentation (version {knowledge['version']}):"
    ]
    for section in knowledge["sections"]:
        lines.append(f"- {section['id']}: {section['title']} — {section['intro']}")
    return "\n".join(lines)


def find(keyword: str) -> str:
    """Locate documentation sections containing a case-insensitive keyword."""
    needle = keyword.strip().casefold()
    if not needle:
        return "(empty keyword)"
    hits: list[str] = []
    for section in load()["sections"]:
        text = _section_text(section)
        folded = text.casefold()
        if needle not in folded:
            continue
        index = folded.find(needle)
        start = max(0, index - 90)
        end = min(len(text), index + len(keyword) + 170)
        snippet = " ".join(text[start:end].split())
        if start > 0:
            snippet = f"…{snippet}"
        if end < len(text):
            snippet = f"{snippet}…"
        hits.append(f"- {section['id']} ({section['title']}): {snippet}")
        if len(hits) >= MAX_FIND_HITS:
            break
    return "\n".join(hits) if hits else "(no documentation matches)"


def read(section_ids: list[str]) -> str:
    """Read complete canonical sections by stable ID."""
    requested = list(dict.fromkeys(value.strip() for value in section_ids if value.strip()))
    if not requested:
        return "(no section IDs supplied)"
    sections = {section["id"]: section for section in load()["sections"]}
    rendered: list[str] = []
    for section_id in requested:
        section = sections.get(section_id)
        if section is None:
            rendered.append(f"[{section_id}] (unknown documentation section)")
        else:
            rendered.append(_section_text(section))
    text = "\n\n".join(rendered)
    if len(text) > MAX_READ_CHARS:
        text = f"{text[:MAX_READ_CHARS]}\n…[truncated; request fewer sections]"
    return text


def _section_text(section: dict[str, Any]) -> str:
    lines = [f"[{section['id']}] {section['title']}", str(section["intro"])]
    for block in section.get("content", []):
        block_type = block.get("type")
        title = block.get("title")
        if title:
            lines.append(str(title))
        if block_type == "steps":
            for index, item in enumerate(block.get("items", []), start=1):
                lines.append(f"{index}. {item['title']}: {item['text']}")
        elif block_type == "definitions":
            for item in block.get("items", []):
                lines.append(f"- {item['term']}: {item['description']}")
        elif block_type in {"note", "warning"}:
            lines.append(str(block.get("text", "")))
        elif block_type == "links":
            for item in block.get("items", []):
                lines.append(
                    f"- {item['title']}: {item['description']} ({item['href']})"
                )
        elif block_type == "faq":
            for item in block.get("items", []):
                lines.append(f"- {item['question']} {item['answer']}")
        elif block_type == "tool_catalog":
            lines.append(
                "- Current tool entries are supplied separately by the workspace catalog."
            )
    return "\n".join(lines)
