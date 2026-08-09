"""Read one reference document and list what it requires of the other.

This is the stage that makes the comparison asymmetric. The design this replaced
extracted units from *both* documents and paired them up, and a pair has no direction:
"annual dosing" beside "every 6 months" and "annual dosing" beside "every 2 years" are
the same pairing, and one of them is a fine candidate while the other is not. Here only
the reference document is mined, and what comes out is a bar — a list the other document
is then measured against, one item at a time.

One call per reference document rather than one per requirement, because the answer is
about the document as a whole: how many requirements it states is precisely what is being
asked. That is the case the suite's one-item-per-request rule exempts, and the same shape
Scout uses to pull units out of a plan.

Nothing here judges anything. A requirement is a quotation of a demand, not an opinion
about whether it was met, and this stage never sees the comparison document.
"""

from __future__ import annotations

from typing import Any

from shared.ai import request_structured

from services.chunker import ContentBlock

from ..models import (
    LLMClientProtocol,
    Requirement,
    requirement_id,
)

_SCOPE_BOUNDARY = """Scope boundary:
- List only what this document requires, commits to, or targets. Background, rationale,
  descriptions of the disease, and statements about other organisations make no demand
  on another document, so they are not requirements.
- Do not judge, rank, or improve anything. You are recording the bar, not assessing it.
- Do not invent a requirement the document implies but does not state. If a target has
  no number, record it as the document words it — a later stage decides whether the
  other document can be measured against it, and that decision needs the real wording.
- One requirement per fact. A sentence setting a shelf life, a storage temperature and a
  presentation states three requirements; split it into three. A single item carrying
  several facts cannot be met or missed as one thing, and forcing one verdict onto it
  loses the part that matters."""


def build_requirements_prompt() -> str:
    """The system prompt for extracting one document's requirements.

    Published through the prompt catalog.
    """
    return f"""You are reading one product-development document and listing every requirement it states, so that a second document can be measured against them.

{_SCOPE_BOUNDARY}

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

For each requirement:
- `text` is one short sentence (max 30 words) stating the requirement in the document's
  own terms, including any number, unit, population, or timeframe it gives. Write it so
  it stands alone: a reader who cannot see the document must know what is being asked.
- `block_ids` MUST cite the exact supplied blocks the requirement was read from. A
  requirement with no citation cannot be checked, and an uncheckable bar is worse than
  a missing one.

List them in the order the document states them. Do not merge two requirements because
they are adjacent, and do not repeat one because it is mentioned twice — cite both
blocks on the single requirement instead."""


def requirements_schema(blocks: list[ContentBlock]) -> dict[str, Any]:
    """The closed shape the extraction must take.

    `block_ids` is an enum of the blocks actually supplied, so a citation to something
    that does not exist is unrepresentable rather than merely invalid.

    There is no cap on how many requirements may come back. The reference document is
    the authority for what it demands, and a cap would quietly redefine the bar as
    "the first N things we happened to read" — which also silently shrinks the
    denominator every count downstream is computed from.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["requirements"],
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "block_ids"],
                    "properties": {
                        "text": {"type": "string"},
                        "block_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [block.id for block in blocks],
                            },
                        },
                    },
                },
            }
        },
    }


def build_user_message(role: str, question: str, blocks: list[ContentBlock]) -> str:
    """What this document is, what the comparison will ask, then the document itself.

    The comparison's question is included because it decides what counts as a
    requirement: measuring a plan against a profile asks about delivery commitments,
    measuring a candidate against an intervention profile asks about product targets.
    The question comes from the edge in `configs/alignment.yaml`, so that framing is
    configuration rather than a branch in this file.
    """
    return "\n\n".join([
        f"This document: {role}",
        f"The comparison that will use these requirements asks: {question}",
        "Document blocks:\n" + _format_blocks(blocks),
    ])


def extract_requirements(
    *,
    edge_id: str,
    role: str,
    question: str,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> list[Requirement]:
    """Every requirement one reference document states, in document order."""
    if not blocks:
        raise ValueError(
            f"Aligner cannot read requirements for {edge_id}: the reference document "
            "parsed to no blocks"
        )
    system_prompt = build_requirements_prompt()
    user_message = build_user_message(role, question, blocks)
    schema = requirements_schema(blocks)
    valid_block_ids = {block.id for block in blocks}

    first_error = "model returned no structured requirements"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior extraction failed the Aligner contract: "
                f"{first_error}. Cite the exact supplied block IDs for every "
                "requirement, and state each requirement in one self-contained "
                "sentence."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="aligner_requirements",
            schema=schema,
            images=_image_inputs(blocks) or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured requirements")
            return _parse_payload(
                payload, edge_id=edge_id, valid_block_ids=valid_block_ids
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(
        f"Aligner could not read the requirements for {edge_id}: {first_error}"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_payload(
    payload: object,
    *,
    edge_id: str,
    valid_block_ids: set[str],
) -> list[Requirement]:
    if not isinstance(payload, dict):
        raise ValueError("extraction must be an object")
    items = payload.get("requirements")
    if not isinstance(items, list) or not items:
        raise ValueError(
            "a reference document states at least one requirement; an empty list "
            "means the extraction failed, not that the document asks for nothing"
        )

    requirements: list[Requirement] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"requirement {index} must be an object")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"requirement {index} has no text")
        # Same wording twice is one requirement cited from two places, and the second
        # copy would double-count in every total downstream.
        key = " ".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)
        block_ids = list(dict.fromkeys(_string_list(item.get("block_ids"))))
        if not block_ids:
            raise ValueError(f"requirement {index} cites no block")
        unknown = [block_id for block_id in block_ids if block_id not in valid_block_ids]
        if unknown:
            raise ValueError(
                f"requirement {index} cites block(s) not in the reference document: "
                f"{unknown}"
            )
        requirements.append(
            Requirement(
                id=requirement_id(edge_id, len(requirements) + 1),
                text=text,
                cited_block_ids=tuple(block_ids),
            )
        )
    return requirements


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _format_blocks(blocks: list[ContentBlock]) -> str:
    return "\n\n".join(
        f"[{block.id}] ({block.source_type} · {block.block_type})\n{block.content}"
        for block in blocks
    )


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    """Slide and figure images, so a requirement stated in a picture is readable."""
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]
