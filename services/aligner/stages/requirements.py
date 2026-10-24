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

from shared.ai import Effort, ModelTask, request_validated
from shared.schemas import non_empty_text
from shared.spans import LINE_SPAN_JSON_INSTRUCTION

from services.chunker import ContentBlock

from ..context import citation_properties, format_blocks, image_inputs, read_spans, read_visual_ids

from ..models import (
    DocumentRole,
    LLMClientProtocol,
    Requirement,
    requirement_id,
)

#: One request per reference document: how many requirements it states is a fact about
#: the whole document, the case the one-item-per-request rule exempts.
DOCUMENTS_PER_REQUEST = 1
#: The reasoning tier at medium effort: splitting a compound sentence into atomic
#: requirements, and leaving background out, is the judgement every verdict inherits.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "medium"
#: Reasoning room, before the answer itself.
BASE_MAX_TOKENS = 8000
#: The largest budget an extraction is given: the reasoning tier's retry ceiling
#: (`shared.ai.MAX_RETRY_TOKENS`). A reference document whose requirements need more is
#: one the request budget would already have refused.
MAX_MAX_TOKENS = 64000


def extraction_budget(document_text: str) -> int:
    """The output budget for one extraction, scaled to the document it reads.

    The answer restates what the document demands, one short sentence and a line range
    per requirement, so it grows with the document and never exceeds it: room for the
    whole document again (about four characters a token), on top of the reasoning
    allowance. A fixed number was either waste on a one-page profile or a cut-off on a
    forty-row target table.
    """
    return min(BASE_MAX_TOKENS + len(document_text) // 4, MAX_MAX_TOKENS)


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

For each requirement:
- `text` is one short sentence (max 30 words) stating the requirement in the document's
  own terms, including any number, unit, population, or timeframe it gives. Write it so
  it stands alone: a reader who cannot see the document must know what is being asked.
- `spans` selects exact source text; `visual_block_ids` selects retained images when
  the requirement is read visually. Supply at least one kind of citation. A visual
  citation is not a verified quotation; never quote an image placeholder. A
  requirement with no citation cannot be checked, and an uncheckable bar is worse than
  a missing one. Select the narrowest range that states the requirement: a table row
  rather than the whole table, one sentence rather than the paragraph around it.

{LINE_SPAN_JSON_INSTRUCTION}

List them in the order the document states them. Do not merge two requirements because
they are adjacent, and do not repeat one because it is mentioned twice — cite both
passages on the single requirement instead."""


def requirements_schema(blocks: list[ContentBlock]) -> dict[str, Any]:
    """The closed shape the extraction must take.

    A citation is a selected line range, never typed text. The model picks a block and
    two line numbers and deterministic code copies those lines out, so a quotation that
    appears in no document cannot be produced - and the block enum is the blocks actually
    supplied, so a citation to something that does not exist is unrepresentable rather
    than merely invalid.

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
                # A reference document states at least one requirement; an empty list
                # is a failed read, and the parser refuses it.
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "spans", "visual_block_ids"],
                    "properties": {
                        "text": non_empty_text(),
                        **citation_properties(blocks),
                    },
                },
            }
        },
    }


def build_user_message(role: DocumentRole, question: str, blocks: list[ContentBlock]) -> str:
    """What this document is, what the comparison will ask, then the document itself.

    The comparison's question is included because it decides what counts as a
    requirement: measuring a plan against a profile asks about delivery commitments,
    measuring a candidate against an intervention profile asks about product targets.
    The question comes from the edge in `configs/alignment.yaml`, so that framing is
    configuration rather than a branch in this file.
    """
    return "\n\n".join([
        f"This document: {role.description}",
        f"The comparison that will use these requirements asks: {question}",
        "Document blocks:\n" + format_blocks(blocks),
    ])


def extract_requirements(
    *,
    edge_id: str,
    role: DocumentRole,
    question: str,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
) -> list[Requirement]:
    """Every requirement one reference document states, in document order."""
    if not blocks:
        raise ValueError(
            f"Aligner cannot read requirements for {edge_id}: the reference document "
            "parsed to no blocks"
        )
    message = build_user_message(role, question, blocks)
    return request_validated(
        llm_client,
        build_requirements_prompt(),
        message,
        schema_name="aligner_requirements",
        schema=requirements_schema(blocks),
        max_tokens=extraction_budget(message),
        task=TASK,
        effort=EFFORT,
        images=image_inputs(blocks) or None,
        parse=lambda payload: _parse_payload(payload, edge_id=edge_id, blocks=blocks),
        repair=lambda error: (
            "\n\nThe prior extraction failed the Aligner contract: "
            f"{error}. For every requirement, select exact [line:N] "
            "ranges in `spans`, retained visual IDs in `visual_block_ids`, or "
            "both, and state each requirement in one self-contained sentence."
        ),
        failure=f"Aligner could not read the requirements for {edge_id}",
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_payload(
    payload: object,
    *,
    edge_id: str,
    blocks: list[ContentBlock],
) -> list[Requirement]:
    if not isinstance(payload, dict):
        raise ValueError("model returned no structured requirements")
    items = payload.get("requirements")
    if not isinstance(items, list) or not items:
        raise ValueError(
            "a reference document states at least one requirement; an empty list "
            "means the extraction failed, not that the document asks for nothing"
        )

    # Every item the model listed is kept. Whether two items are one requirement is the
    # extraction's judgement about the document; lowercasing and comparing their
    # wording here would be string normalization deciding identity, and two
    # requirements that read alike can cite different rows of a table.
    requirements: list[Requirement] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"requirement {index} must be an object")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"requirement {index} has no text")
        spans = read_spans(item.get("spans"), blocks)
        visual_ids = read_visual_ids(item.get("visual_block_ids"), blocks)
        if not spans and not visual_ids:
            raise ValueError(
                f"requirement {index} selected no source text or retained visual in the "
                "reference document"
            )
        requirements.append(
            Requirement(
                id=requirement_id(edge_id, index),
                text=text,
                cited_spans=tuple(spans),
                visual_block_ids=tuple(visual_ids),
            )
        )
    return requirements
