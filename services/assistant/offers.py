"""Things the reader can do next, proposed by the agent and never done by it.

Ask is read-only and never runs an evidence search. When a question needs evidence the
workspace does not hold, the useful answer is not "I can't" but the search that would
find it, set up for the reader to run. An offer is that proposal: structured, so the
interface can render it as a control and prefill the tool it opens, and inert, so nothing
happens until the reader acts.

An offer travels on its own stream event rather than inside the answer text. The answer
is prose for a reader; an offer is data for the interface, and parsing one out of the
other is the re-reading of finished text this codebase avoids.

What a search accepts and what each field means is Searcher's to say. The fields and their
descriptions come from `searcher.SEARCH_TEXT_FIELDS`, the sources from Searcher's registry,
the entity types from its vocabulary, so a field or source added to Searcher reaches the
offer without an edit here. Only the rules for when an offer states something belong here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.searcher import (
    ENTITY_TYPES,
    SEARCH_ENTITIES_DESCRIPTION,
    SEARCH_ENTITY_FIELDS,
    SEARCH_TEXT_FIELDS,
    source_specs,
)

#: When an offer states a field, beyond what the field means. A suggestion is made for a
#: reader's question, so it narrows only where that question did.
OFFER_RULES: dict[str, str] = {
    "published_since": "Only if the reader asked for recent evidence.",
    "entities": "Only when the question names one and a chosen source needs it.",
}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Longest value kept per field. An offer is a starting point a reader edits, not a document.
MAX_FIELD_CHARS = 300
#: Most entities an offer names. A search addressed to more subjects than this is several searches.
MAX_ENTITIES = 5


@dataclass(frozen=True)
class SearchOffer:
    """A Searcher run, filled in for the reader to review and start."""

    #: Searcher's text fields that were stated, by Searcher's names; always includes `query`.
    fields: dict[str, str]
    #: Registered source keys chosen for this question; empty leaves Searcher's defaults.
    sources: tuple[str, ...] = ()
    #: Named subjects for sources that address one, as (name, entity type).
    entities: tuple[tuple[str, str], ...] = ()

    def to_event(self) -> dict[str, Any]:
        """What the interface receives: the tool it opens, and only what was stated."""
        labels = {spec.key: spec.label for spec in source_specs()}
        event: dict[str, Any] = {"tool": "searcher", "fields": dict(self.fields)}
        if self.sources:
            event["sources"] = [{"key": key, "label": labels[key]} for key in self.sources]
        if self.entities:
            event["entities"] = [{"name": name, "entity_type": kind} for name, kind in self.entities]
        return event


def offer_parameters() -> dict[str, Any]:
    """The tool schema for `offer_search`, built from what Searcher accepts.

    Sources are offered as an enum of registered keys, each described by what it covers, so
    the agent chooses among sources that exist rather than naming one. Whether a source is
    configured on this server is checked again where the reader opens Searcher, which only
    ticks sources it can run.
    """
    sources = sorted(source_specs(), key=lambda spec: spec.key)
    catalogue = "; ".join(
        f"{spec.key} ({spec.evidence_class}, {spec.jurisdiction}"
        + (f", needs an entity of type {'/'.join(spec.required_entity_types)}" if spec.required_entity_types else "")
        + ")"
        for spec in sources
    )
    return {
        "type": "object",
        "properties": {
            **{
                name: {"type": "string", "description": _described(meaning, name)}
                for name, meaning in SEARCH_TEXT_FIELDS.items()
            },
            "sources": {
                "type": "array",
                "items": {"type": "string", "enum": [spec.key for spec in sources]},
                "description": (
                    "Sources the question needs, chosen by what each covers; leave empty for Searcher's "
                    f"general defaults. Available: {catalogue}."
                ),
            },
            "entities": {
                "type": "array",
                "maxItems": MAX_ENTITIES,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "description": SEARCH_ENTITY_FIELDS["name"]},
                        "entity_type": {
                            "type": "string", "enum": sorted(ENTITY_TYPES),
                            "description": SEARCH_ENTITY_FIELDS["entity_type"],
                        },
                    },
                    "required": ["name", "entity_type"],
                },
                "description": _described(SEARCH_ENTITIES_DESCRIPTION, "entities"),
            },
        },
        "required": ["query"],
    }


def _described(meaning: str, name: str) -> str:
    """Searcher's description of a field, with the offer's rule for stating it, if any."""
    return f"{meaning} {OFFER_RULES[name]}" if name in OFFER_RULES else meaning


def search_offer(args: dict[str, Any]) -> SearchOffer | str:
    """The offer the model proposed, or why it cannot be made.

    Model arguments are untrusted: non-strings are dropped, values are trimmed and bounded,
    a date that is not ISO is dropped rather than passed to a field that would refuse it,
    and a source or entity type Searcher does not declare is dropped rather than guessed at.
    """
    fields = {
        name: str(args[name]).strip()[:MAX_FIELD_CHARS]
        for name in SEARCH_TEXT_FIELDS
        if isinstance(args.get(name), str) and args[name].strip()
    }
    if not fields.get("query"):
        return "No search was offered: a query is required."
    if "published_since" in fields and not _ISO_DATE.match(fields["published_since"]):
        del fields["published_since"]
    known = {spec.key for spec in source_specs()}
    raw_sources = args.get("sources") if isinstance(args.get("sources"), list) else []
    sources = tuple(dict.fromkeys(key for key in raw_sources if isinstance(key, str) and key in known))
    raw_entities = args.get("entities") if isinstance(args.get("entities"), list) else []
    entities = tuple(dict.fromkeys(
        (str(item["name"]).strip()[:MAX_FIELD_CHARS], item["entity_type"])
        for item in raw_entities
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()
        and item.get("entity_type") in ENTITY_TYPES
    ))[:MAX_ENTITIES]
    return SearchOffer(fields=fields, sources=sources, entities=entities)
