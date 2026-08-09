"""Workflows the assistant can follow, declared as files rather than prompt text.

A skill is bespoke: its own procedure, its own synthesis rules, its own output
shape. Embedding those in the system prompt would pay for every workflow on every
message and put unrelated instructions in one another's way. So the index is
resident and cheap — a name and a line each — and a body is read only once chosen.

`requires` is the field that keeps selection honest. A skill naming two result
types is not offered when the workspace holds one of them, and the same
declaration is what tells the user which run is missing. Without it, both would be
prose repeated in every skill and true only until a result shape changed.

Adding a skill is one file. No agent change, no registry edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# The result types a skill may require. Kept as one closed set so a typo in
# frontmatter fails at load rather than silently making a skill unofferable.
KNOWN_RESULT_TYPES = frozenset(
    {"inspector", "aligner", "scout", "chunker", "searcher", "expert"}
)

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


@dataclass(frozen=True)
class Skill:
    """One declared workflow."""

    name: str
    description: str
    requires: tuple[str, ...]
    body: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a skill must declare a name")
        if not self.description:
            raise ValueError(f"skill {self.name} must declare a description")
        unknown = [item for item in self.requires if item not in KNOWN_RESULT_TYPES]
        if unknown:
            raise ValueError(
                f"skill {self.name} requires unknown result type(s): {', '.join(unknown)}"
            )
        if not self.body.strip():
            raise ValueError(f"skill {self.name} has no body")


def _parse(path: Path) -> Skill:
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path.name} has no frontmatter block")
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path.name} frontmatter is not a mapping")
    requires = meta.get("requires") or []
    return Skill(
        name=str(meta.get("name", path.stem)).strip(),
        description=str(meta.get("description", "")).strip(),
        requires=tuple(str(item).strip() for item in requires),
        body=match.group(2).strip(),
    )


def available_skills() -> list[Skill]:
    """Every declared workflow, in stable order.

    Mirrors `available_configs` in the services: what exists is decided by what
    loads, not by a list someone has to remember to update.
    """
    if not SKILLS_DIR.exists():
        return []
    return [_parse(path) for path in sorted(SKILLS_DIR.glob("*.md"))]


def find_skill(name: str) -> Skill | None:
    wanted = name.strip().casefold()
    for skill in available_skills():
        if skill.name.casefold() == wanted:
            return skill
    return None


def catalog(held_result_types: frozenset[str] | set[str] | None = None) -> str:
    """The resident index: what exists, and what each one still needs.

    Unavailable skills are listed rather than hidden. A user asking to compare
    drift against evidence should be told a Scout run is missing, not told the
    workflow does not exist.
    """
    skills = available_skills()
    if not skills:
        return "No workflows are available."
    held = frozenset(held_result_types or frozenset())
    lines: list[str] = []
    for skill in skills:
        missing = [item for item in skill.requires if item not in held]
        state = (
            f" — needs a {', '.join(missing)} result the workspace does not hold"
            if missing
            else " — ready"
        )
        lines.append(f"- {skill.name}: {skill.description}{state}")
    return "\n".join(lines)


def read_skill(name: str) -> str:
    """The full procedure, once the agent has chosen it."""
    skill = find_skill(name)
    if skill is None:
        known = ", ".join(item.name for item in available_skills()) or "none"
        return f"No workflow named {name!r}. Available: {known}."
    return skill.body
