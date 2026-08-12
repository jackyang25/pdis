"""One read over a finished result: what its priorities add up to, and what they miss.

Two things a tool's own selector cannot produce, and they are deliberately separate:

    digest       one short passage about the list already on screen
    nominations  items the selector excluded that are worth a second look

The selector stays the authority for what qualifies and in what order. This module never
reorders it, never adds to it, and never overturns a verdict — the panel's promise is that
the wording is the model's and the ranking is not, and a model that could re-sort the list
would make that sentence false.

It is one call because the two outputs need the same context and the nomination half needs
to know what the deterministic half already covers. Told nothing about the list, a model
asked for "anything else worth looking at" returns the list.

Nothing here is stored. The digest describes a list that is itself derived on read, so
freezing it into a result would leave a paragraph describing a list that changed under it.

Agnostic by construction: no tool name, no document type and no indication appears in the
prompt. The caller supplies the authority sentence the tool already publishes in the
catalog, the context tags every result carries, and the items as the panel rendered them.
A fifth tool is served by this file unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from shared.ai import request_structured
from shared.openai_client import ModelTask
from shared.vocabulary import search_term

#: Most nominations a reader is offered.
#:
#: This is a second look, not a second list: the deterministic panel is already the answer
#: to "what should I read first", and a nomination layer long enough to scroll competes
#: with it instead of adding to it.
MAX_NOMINATIONS = 3

#: Longest digest, in words. Enough for two short paragraphs.
MAX_DIGEST_WORDS = 130

#: Most block IDs that may be offered as a closed enum.
#:
#: Structured outputs cap an enum past 250 values at 7,500 characters of total string
#: length, and a block ID runs about fifteen characters, so a result holding more than a
#: few hundred blocks makes the schema itself invalid and the provider rejects the whole
#: request. That is not a degraded answer, it is no answer: the panel showed a skeleton
#: and then nothing, on exactly the results that have the most to say.
#:
#: Above the bound the IDs are left unenumerated and `_parse_payload` does the checking it
#: already did — a citation naming a block the result does not hold is dropped either way,
#: so the enum was belt to that braces rather than the guarantee itself.
MAX_ENUMERATED_BLOCK_IDS = 240


class LLMClientProtocol(Protocol):
    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        task: ModelTask = "reasoning",
    ) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True)
class PriorityItemInput:
    """One item exactly as the panel rendered it."""

    id: str
    label: str
    qualifier: str = ""
    statement: str = ""
    recommendation: str = ""


@dataclass(frozen=True)
class PriorityRequest:
    """Everything the read needs, all of it already published by the caller."""

    #: The tool's catalog sentence: what it reads, and the authority it judges against.
    #: Passed rather than looked up so this module holds no tool table.
    authority: str
    #: How the deterministic list was ordered, in the tool's own words.
    order_note: str
    items: tuple[PriorityItemInput, ...]
    #: The result's analysis, without its blocks. The nomination half reads this,
    #: because what the selector excluded is by definition not in the selector's output.
    analysis: Any
    #: Every block ID the result carries, so a citation can be checked against it.
    block_ids: frozenset[str] = frozenset()
    org: str = ""
    intervention_class: str = ""
    indication: str = ""


@dataclass
class Nomination:
    """One thing the selector left out, and where to look at it."""

    label: str
    statement: str
    cited_block_ids: list[str] = field(default_factory=list)


@dataclass
class PriorityDigest:
    digest: str
    nominations: list[Nomination] = field(default_factory=list)


def build_system_prompt() -> str:
    """The one prompt, for every tool. Names none of them."""
    return f"""You are reading one finished analysis and the list of priorities a tool has already selected from it.

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

You produce two things, and they must not do each other's job.

`digest`: at most {MAX_DIGEST_WORDS} words, one or two short paragraphs, about the items in
the list you were given and nothing else.
- Say what the list amounts to: what kind of thing keeps recurring, where it concentrates,
  what a reader is looking at as a whole. A reader who has the list already can see the
  items; what they cannot see is the shape.
- Name the authority the tool judged against. A sentence saying a document "has gaps"
  without saying what it was held to is the sentence most likely to be repeated wrongly.
- Do NOT introduce an item that is not in the list, do not re-rank the list, do not say
  which item is most important, and do not score or total anything. The order was decided
  by a stated rule and is not yours to revise.
- Do not restate items one by one. A digest that walks the list is the list again.
- Written to be read on screen beside the list, so no citations and no identifiers.

`nominations`: at most {MAX_NOMINATIONS}, and fewer or none is the normal answer.
- Something in the analysis that the selected list does NOT contain and that a reader of
  this list would want to know. A finding the rule filtered out, a pattern across several
  findings, a value that is fine on its own but sits under something else that is not.
- Never a repeat of a listed item in different words. If everything worth raising is
  already in the list, return an empty array — that is a good answer and the common one.
- `statement`: one or two sentences, factual, saying what it is and why a reader of this
  list would care. Never an instruction, never a severity, never a ranking against the
  listed items.
- `cited_block_ids`: the exact document block IDs the nomination rests on, drawn from the
  IDs supplied. A nomination you cannot point at is a nomination you cannot make, so if
  nothing in the analysis carries block IDs for it, leave it out entirely.

Scope boundary:
- You do not judge the product, the targets, or the documents. The tool already judged;
  you are reading its output.
- You do not overturn, soften or contradict a verdict, a state or a grade. Where you think
  the analysis is wrong, that is not a nomination.
- You do not use your own knowledge of the field to add a finding. Everything you say
  comes from the analysis in front of you.
- The domain is context for reading, never a source. Knowing the intervention class and
  indication tells you which findings are consequential; it does not license a claim
  neither the analysis nor its documents make."""


#: Longest the analysis may be inside the prompt, in characters.
#:
#: The digest half needs only the list it describes; the nomination half needs the
#: analysis, and analyses differ by an order of magnitude between tools — a rubric
#: assessment against a run holding matches, insights, precedents and a landscape. Rather
#: than project each tool's result into a shape this file would have to know about, the
#: bound is stated once and the nomination half stands down when a result exceeds it. A
#: digest that describes the list is still worth having; nominations invented from a
#: truncated view are not.
MAX_ANALYSIS_CHARACTERS = 120_000


def build_user_message(request: PriorityRequest) -> str:
    """Context, then the list, then the analysis.

    The list before the analysis on purpose: the first question is "what is already
    covered", and a model that reads the analysis first tends to answer with it.
    """
    context = [f"The tool: {request.authority}"]
    domain = " · ".join(
        part
        for part in (
            request.org,
            search_term(request.intervention_class),
            search_term(request.indication),
        )
        if part
    )
    if domain:
        context.append(f"Run context: {domain}")
    if request.order_note:
        context.append(f"How the list below was ordered: {request.order_note}")

    listed = "\n\n".join(
        "\n".join(
            part
            for part in (
                f"[{item.id}] {item.label}",
                f"  where: {item.qualifier}" if item.qualifier else "",
                f"  finding: {item.statement}" if item.statement else "",
                f"  recommended: {item.recommendation}" if item.recommendation else "",
            )
            if part
        )
        for item in request.items
    ) or "(the tool selected nothing)"

    analysis = str(request.analysis)
    if len(analysis) > MAX_ANALYSIS_CHARACTERS:
        # Said plainly rather than truncated. A model handed half an analysis with no note
        # would nominate from the half it saw and present it as a reading of the whole.
        return "\n\n".join([
            "\n".join(context),
            f"Priorities already selected and shown to the reader ({len(request.items)}):\n{listed}",
            "The full analysis is too large to include, so return an empty `nominations` "
            "array: you have not seen enough to say what the list leaves out. Write the "
            "digest from the list above, which is all it describes.",
        ])
    return "\n\n".join([
        "\n".join(context),
        f"Priorities already selected and shown to the reader ({len(request.items)}):\n{listed}",
        f"The full analysis:\n{analysis}",
    ])


def digest_schema(block_ids: Sequence[str]) -> dict[str, Any]:
    """The closed shape, with citations restricted to blocks that exist."""
    ids = list(dict.fromkeys(block_ids))
    # Enumerated only while the enum is small enough to be valid. Empty is excluded for
    # the same reason from the other end: no provider accepts an empty enum.
    enumerable = 0 < len(ids) <= MAX_ENUMERATED_BLOCK_IDS
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["digest", "nominations"],
        "properties": {
            "digest": {"type": "string"},
            "nominations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "statement", "cited_block_ids"],
                    "properties": {
                        "label": {"type": "string"},
                        "statement": {"type": "string"},
                        "cited_block_ids": {
                            "type": "array",
                            "items": (
                                {"type": "string", "enum": ids}
                                if enumerable
                                else {"type": "string"}
                            ),
                        },
                    },
                },
            },
        },
    }


def read_priorities(
    request: PriorityRequest,
    *,
    llm_client: LLMClientProtocol,
    max_tokens: int = 1200,
) -> PriorityDigest:
    """One digest and up to `MAX_NOMINATIONS` nominations, both validated."""
    payload = request_structured(
        llm_client,
        build_system_prompt(),
        build_user_message(request),
        max_tokens=max_tokens,
        schema_name="priority_digest",
        schema=digest_schema(sorted(request.block_ids)),
    )
    if payload is None:
        raise ValueError("model returned no priority digest")
    return _parse_payload(payload, request)


def _parse_payload(payload: object, request: PriorityRequest) -> PriorityDigest:
    if not isinstance(payload, dict):
        raise ValueError("digest must be an object")
    digest = " ".join(str(payload.get("digest") or "").split())
    if not digest:
        raise ValueError("a digest that says nothing is worse than none")

    listed_labels = {_key(item.label) for item in request.items}
    nominations: list[Nomination] = []
    for entry in payload.get("nominations") or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        statement = str(entry.get("statement") or "").strip()
        if not label or not statement:
            continue
        # A nomination repeating a listed item would give one finding two layers, so the
        # rule is enforced here rather than trusted to the prompt.
        if _key(label) in listed_labels:
            continue
        cited = [
            block_id
            for block_id in dict.fromkeys(
                str(item).strip() for item in entry.get("cited_block_ids") or []
            )
            if block_id in request.block_ids
        ]
        # Dropped rather than shown unsourced: the panel's whole claim is that everything
        # in it can be opened.
        if request.block_ids and not cited:
            continue
        nominations.append(
            Nomination(label=label, statement=statement, cited_block_ids=cited)
        )
        if len(nominations) == MAX_NOMINATIONS:
            break
    return PriorityDigest(digest=digest, nominations=nominations)


def _key(text: str) -> str:
    return " ".join(text.lower().split())
