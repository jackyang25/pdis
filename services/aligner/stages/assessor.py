"""Ask, for one requirement, what the other document does with it.

One schema-bound call per requirement. The verdict is a single closed enum, and the
enum is asymmetric on purpose: `exceeds` and `falls_short` are the same difference read
in opposite directions, and the vocabulary this replaced could not tell them apart, so
a candidate that beat its target and one that missed it by years carried the same label.

    meets           the comparison document satisfies the requirement
    exceeds         it does better than the requirement asks
    falls_short     it addresses the requirement but does less than it asks
    not_comparable  it addresses the subject in terms that cannot be measured against
                    the requirement, so neither meeting nor missing can be claimed
    not_addressed   it says nothing on the subject

The schema offers only the comparison document's block IDs, so a verdict cannot be
justified by citing the document that set the bar. That is the one guarantee worth
having here: "the candidate says X" always points into the candidate's own file.
"""

from __future__ import annotations

from typing import Any

from shared.ai import request_structured

from services.chunker import ContentBlock

from ..models import (
    ALIGNMENT_VERDICTS,
    AlignmentFinding,
    LLMClientProtocol,
    Requirement,
    VERDICTS_REQUIRING_CITATION,
    VERDICTS_REQUIRING_GAP,
)

# One requirement per request. Another requirement in this prompt would influence the
# verdict — a document that meets four targets reads as compliant on the fifth — and
# batch composition would shift between runs. Throughput comes from fan-out in the
# pipeline, never from packing requirements together.
REQUIREMENTS_PER_REQUEST = 1

_SCOPE_BOUNDARY = """Scope boundary:
- Decide only what this document does with this requirement. Do not judge how well
  either document is written, whether it follows a template, or whether the requirement
  itself is sensible. Those are other tools' jobs and a verdict here would contradict
  them.
- Do not use your own knowledge of the field to fill either side. The requirement is
  whatever the reference document asked for; the answer is whatever this document
  states. If it does not state it, that is the finding.
- The comparison runs one way. You are not describing how the two documents differ; you
  are deciding whether this one meets a bar the other one set."""


def build_assessment_prompt() -> str:
    """The system prompt for one requirement. Published through the prompt catalog."""
    return f"""You are checking one product-development document against a single requirement taken from another document.

{_SCOPE_BOUNDARY}

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Verdicts:
- meets: this document states something that satisfies the requirement. Cite the blocks.
- exceeds: it states something better than the requirement asks — sooner, cheaper,
  longer, broader. Cite the blocks, and say in `gap` nothing at all.
- falls_short: it addresses the requirement and states less than it asks. Cite the
  blocks, and put in `gap` one short sentence naming the distance — what the
  requirement asks for against what this document offers.
- not_comparable: it addresses the same subject but not in terms that can be measured
  against the requirement — a qualitative claim against a numeric bar, a different
  population, a different endpoint. Cite the blocks, and put in `gap` one short
  sentence naming what would have to be stated for the two to be comparable. Use this
  rather than guessing: reporting `falls_short` here would assert this document is
  worse, which it does not say.
- not_addressed: nothing in this document speaks to the requirement. Leave `block_ids`
  empty and `gap` blank. This is the right answer for a requirement this document was
  never meant to carry as much as for one it should have.

Lineage is required, not optional. Every verdict except `not_addressed` MUST cite the
exact supplied block IDs it was read from. A citation you cannot point at is worse than
reporting the requirement unaddressed.

`statement` is one short factual sentence (max 25 words) saying what this document
states on the subject, or that it states nothing. Describe the document; do not instruct
the reader, and do not restate the requirement.

`gap` is one short sentence (max 25 words), on `falls_short` and `not_comparable` and
nowhere else. It is read as the thing to take back to whoever wrote this document, so
name what is needed rather than what is absent: "24-month shelf life against the 36
months required" rather than "the shelf life is not good enough"."""


def assessment_schema(blocks: list[ContentBlock]) -> dict[str, Any]:
    """The closed shape one verdict must take.

    `block_ids` enumerates the **comparison** document's blocks and nothing else, which
    is how the direction of the comparison survives into the citation: the model cannot
    prove a candidate meets a bar by pointing at the document that set it.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "statement", "gap", "block_ids"],
        "properties": {
            "verdict": {"type": "string", "enum": list(ALIGNMENT_VERDICTS)},
            "statement": {"type": "string"},
            # Always present, blank unless the verdict requires it. A conditional
            # requirement is the one thing this schema cannot express, so the verdict
            # carries the condition and code checks the pairing.
            "gap": {"type": "string"},
            "block_ids": {
                "type": "array",
                "items": {"type": "string", "enum": [block.id for block in blocks]},
            },
        },
    }


def build_user_message(
    requirement: Requirement,
    role: str,
    question: str,
    blocks: list[ContentBlock],
) -> str:
    """The comparison document first, the requirement last.

    Order matters for cost, not for reading. Every requirement on one edge is judged
    against the same document, so putting that document first makes it a prompt prefix a
    provider can cache: the expensive half is paid for once per comparison instead of
    once per requirement.

    The reference document's blocks are deliberately absent. Only the one requirement
    crosses over, because handing the whole bar across would invite the model to
    re-derive which requirement matters, and the requirement's own citation is how a
    reader checks the bar instead.
    """
    return "\n\n".join([
        f"This document: {role}",
        f"The question being answered: {question}",
        "Document blocks:\n" + _format_blocks(blocks),
        f"Requirement to check ({requirement.id}):\n{requirement.text}",
    ])


def assess_requirement(
    requirement: Requirement,
    *,
    edge_id: str,
    role: str,
    question: str,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> AlignmentFinding:
    """One verdict about one requirement, with its lineage validated."""
    system_prompt = build_assessment_prompt()
    user_message = build_user_message(requirement, role, question, blocks)
    schema = assessment_schema(blocks)
    valid_block_ids = {block.id for block in blocks}

    first_error = "model returned no structured verdict"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior verdict failed the Aligner contract: "
                f"{first_error}. Cite the exact supplied block IDs unless the "
                "requirement is not addressed at all, and name the distance in `gap` "
                "when the document falls short or cannot be compared."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="aligner_requirement_verdict",
            schema=schema,
            images=_image_inputs(blocks) or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured verdict")
            return _parse_payload(
                payload,
                requirement=requirement,
                edge_id=edge_id,
                valid_block_ids=valid_block_ids,
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(
        f"Aligner could not judge {requirement.id}: {first_error}"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_payload(
    payload: object,
    *,
    requirement: Requirement,
    edge_id: str,
    valid_block_ids: set[str],
) -> AlignmentFinding:
    if not isinstance(payload, dict):
        raise ValueError("verdict must be an object")
    verdict = payload.get("verdict")
    if verdict not in ALIGNMENT_VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}")

    statement = str(payload.get("statement") or "").strip()
    if not statement:
        raise ValueError("every verdict must carry a statement")

    finding = requirement.finding(edge_id, verdict)  # type: ignore[arg-type]
    finding.statement = statement

    gap = str(payload.get("gap") or "").strip()
    if verdict in VERDICTS_REQUIRING_GAP and not gap:
        raise ValueError(
            f"{verdict} must name the distance from the requirement, because that "
            "sentence is the only account of what is actually missing"
        )
    if gap and verdict not in VERDICTS_REQUIRING_GAP:
        raise ValueError(
            f"{verdict} cannot carry a gap: the requirement is either satisfied or "
            "not addressed at all"
        )
    finding.gap = gap

    block_ids = list(dict.fromkeys(_string_list(payload.get("block_ids"))))
    if verdict in VERDICTS_REQUIRING_CITATION:
        if not block_ids:
            raise ValueError(f"{verdict} must cite the passages it was read from")
        unknown = [block_id for block_id in block_ids if block_id not in valid_block_ids]
        if unknown:
            raise ValueError(
                f"cited block(s) that are not in the document being checked: {unknown}"
            )
    elif block_ids:
        raise ValueError(
            "not_addressed cannot cite a passage: it is a claim about the absence of one"
        )
    finding.comparison_block_ids = block_ids
    return finding


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
    """Slide and figure images, so a commitment made in a picture is readable."""
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]
