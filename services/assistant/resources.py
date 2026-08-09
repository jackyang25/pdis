"""The one registry of everything the Ask agent can reach.

A capability used to be spread across three places that did not know about each
other: a hand-written tool schema, whatever the system prompt claimed existed,
and the label a reader sees while it runs. Nothing connected them, so they drifted
independently and only a person noticing could catch it.

Here each capability is declared once. The tool schemas the model is offered, the
activity a reader sees, and the inventory the system prompt states are all derived
from these entries, so they cannot disagree. Adding a capability is one entry.

`kind` is the distinction the shape alone would lose: a document and a workflow are
both fetched the same way, but one is evidence to cite and the other is procedure to
follow. Declaring it lets the system prompt say so once instead of every skill
repeating it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ResourceKind = Literal["evidence", "procedure"]

# What the agent is doing, in the reader's words. Held beside the schema so a new
# capability cannot ship with a tool and no label.
Handler = Callable[..., str]


@dataclass(frozen=True)
class Verb:
    """One callable the model may invoke, and what to show while it runs."""

    name: str
    description: str
    activity: str
    parameters: dict[str, Any]
    handler: Handler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class Resource:
    """One thing the agent can reach, and every way it may reach it."""

    key: str
    summary: str
    kind: ResourceKind
    verbs: tuple[Verb, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.verbs:
            raise ValueError(f"resource {self.key} declares no verbs")


def tool_schemas(resources: tuple[Resource, ...]) -> list[dict[str, Any]]:
    """Every verb, as the model is offered it."""
    return [verb.schema() for resource in resources for verb in resource.verbs]


def verbs_by_name(resources: tuple[Resource, ...]) -> dict[str, Verb]:
    """Dispatch table. Duplicate names would silently shadow, so they raise."""
    table: dict[str, Verb] = {}
    for resource in resources:
        for verb in resource.verbs:
            if verb.name in table:
                raise ValueError(f"two resources declare the verb {verb.name!r}")
            table[verb.name] = verb
    return table


def activity_for(resources: tuple[Resource, ...], verb_name: str) -> str:
    """What a reader is told while `verb_name` runs."""
    verb = verbs_by_name(resources).get(verb_name)
    return verb.activity if verb else "Working"


def inventory(resources: tuple[Resource, ...]) -> str:
    """The agent's own map of its world, for the system prompt.

    Generated rather than written, so the prompt cannot claim a capability that
    no longer exists or omit one that was added.
    """
    lines: list[str] = []
    for resource in resources:
        names = ", ".join(verb.name for verb in resource.verbs)
        note = " (procedure to follow, never evidence to cite)" if resource.kind == "procedure" else ""
        lines.append(f"- {resource.summary}{note}: {names}")
    return "\n".join(lines)
