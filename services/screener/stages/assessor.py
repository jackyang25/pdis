"""Assess one gate question against all retained document blocks.

Every answer cites supplied block IDs. The three model decisions map directly
onto result states; only configuration can declare a question not applicable.
"""

from __future__ import annotations

from typing import Any

from shared.ai import request_structured
from shared.document_metadata import extraction_context

from services.chunker import ContentBlock

from ..models import (
    LLMClientProtocol,
    MODEL_STATES,
    QuestionAssessment,
    QuestionSpec,
)

# One question per request. An unrelated question in this prompt would influence
# the decision, and batch composition would shift between runs. Throughput comes
# from fan-out in the pipeline, never from packing questions together.
QUESTIONS_PER_REQUEST = 1

DECISION_ANSWERED = "answered"
DECISION_PARTLY_ANSWERED = "partly_answered"
DECISION_NOT_FOUND = "not_found"

_SCOPE_BOUNDARY = """Scope boundary:
- You are deciding only whether the supplied material ANSWERS the question. Do not
  judge how well the documents are written, whether they follow a template, or
  whether their targets are realistic. Those are other tools' jobs and a verdict
  here would contradict them.
- Do not answer the question yourself from your own knowledge. A question is
  answered only when the supplied material answers it.
- These questions are compound: many ask two or three things in one sentence. Judge
  them clause by clause. Every clause answered is answered; some answered is partly;
  none is not found. Do not round a partial up or down.

How to read one of these questions:
- A list in parentheses tells you what counts as addressing the term in front of it. It
  is not a checklist of separate demands. "the physicochemical properties (crystallinity,
  solubility/pKa, LogP/LogD, permeability, Lipinski)" asks about the properties, and the
  list is how you recognise material that addresses them. Material that covers the term
  substantively is answered. It is partly only when it addresses the term and visibly
  leaves out something the question singles out — and then `missing` names that thing.
- A list after a dash or a colon is different: there the author is enumerating what they
  want, so each item is its own clause and an omission is a partial.
- A question asking whether something is planned, being initiated, being scoped, under
  way or under consideration is answered when the material states that it is. It does
  not require the plan to be finished or the activity to be complete — that is what a
  later gate asks.
- A question asking whether something has been assessed, evaluated, screened or
  characterised is answered when the material carries the substance of it. A document
  states findings; it rarely narrates who produced them, and requiring it to name the
  people or the process would make almost everything partial.
- Judge the question in front of you, not the one you would have asked. Where the
  question is looser than you would like, it is answered by material that satisfies it as
  written."""


def build_assessment_prompt() -> str:
    """The system prompt for one question. Published through the prompt catalog."""
    decisions = [
        f"- {DECISION_ANSWERED}: the supplied document blocks answer every part "
        "of the question. Cite in `block_ids` every block you read to reach that.",
        f"- {DECISION_PARTLY_ANSWERED}: the documents answer some parts and leave "
        "others open. Cite the blocks, and put in `missing` one short sentence naming "
        "exactly what is still not stated.",
    ]
    decisions.append(
        f"- {DECISION_NOT_FOUND}: nothing supplied addresses the question at all. "
        "Leave `block_ids` empty and `missing` blank. This is the "
        "right answer for a question the supplied material was never going to contain "
        "— an operational check, or a matter of judgment — as much as for one it "
        "should have."
    )
    return f"""You are triaging one stage-gate review question against a set of product-development documents.

{_SCOPE_BOUNDARY}

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Decisions:
{chr(10).join(decisions)}

Lineage is required, not optional. `{DECISION_ANSWERED}` MUST cite the exact
supplied block IDs it was read from. A citation you cannot point at is worse than
reporting the question unanswered.

`statement` is one short factual sentence (max 25 words) saying what the material states,
or that it states nothing on the subject. Say what it holds, not how much of the question
it covers — the state already says that, and `missing` says the rest.

On a partial, `statement` and `missing` divide the question between them and must not
overlap: `statement` is the part that IS addressed and `missing` is the part that is not,
so a reader can see both halves without opening the document. Name the specific thing in
each. "Stability is partly covered" tells a reader nothing; "Zones I and II are covered"
plus "Zone IVb data and the VVM category" tells them what to ask for.

`missing` is one short sentence (max 25 words) naming only what is still not stated, on a
partial answer and nowhere else. It is read as an instruction to whoever wrote the
document, so name the thing, not its absence: "Zone IVb stability data and the VVM
category" rather than "the document does not say". Never restate the whole question there:
if every part is missing the answer is not_found, and if the missing part cannot be named
specifically then the question is answered.

Describe the material; do not instruct the reader, and do not restate the question."""


def assessment_schema(
    blocks: list[ContentBlock],
) -> dict[str, Any]:
    """A decision over supplied blocks, with no unretained evidence source."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision",
            "statement",
            "missing",
            "block_ids",
        ],
        "properties": {
            "decision": {"type": "string", "enum": list(MODEL_STATES)},
            "statement": {"type": "string", "minLength": 1},
            # Always present, blank unless the decision is a partial. A conditional
            # requirement is the one thing this schema cannot express, so the decision
            # carries the condition and code checks the pairing.
            "missing": {"type": "string"},
            "block_ids": {
                "type": "array",
                "items": {"type": "string", "enum": [block.id for block in blocks]},
            },
        },
    }


def build_user_message(
    question: QuestionSpec,
    blocks: list[ContentBlock],
) -> str:
    """The supplied material first, the question last.

    Order matters for cost, not for reading. Every question in a run receives the same
    documents, so putting them first makes them a prompt prefix a
    provider can cache: the expensive half is paid for once instead of once per
    question. With the question first — as this was — every call had a different first
    line and shared nothing.

    The bank's `requirement` is deliberately absent. Whether a gate requires this now or
    expects it to be forming is a fact about the review, not about the documents, and a
    model told a question is only "anticipatory" would read the material less carefully
    for it. The same triage runs either way; the distinction is for the reader.
    """
    parts = ["Supplied document blocks:\n" + _format_blocks(blocks)]
    parts.append(f"Question ({question.id}):\n{question.text}")
    return "\n\n".join(parts)


def assess_question(
    question: QuestionSpec,
    *,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> QuestionAssessment:
    """One decision about one question, with its lineage validated."""
    system_prompt = build_assessment_prompt()
    user_message = build_user_message(question, blocks)
    schema = assessment_schema(blocks)
    images = _image_inputs(blocks)
    valid_block_ids = {block.id for block in blocks}

    first_error = "model returned no structured decision"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior decision failed the Screener contract: "
                f"{first_error}. Cite the exact supplied block IDs when answering "
                "and cite nothing when the question is unanswered."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="screener_question_triage",
            schema=schema,
            images=images or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured decision")
            return _parse_payload(
                payload,
                question=question,
                valid_block_ids=valid_block_ids,
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(f"Screener could not triage {question.id}: {first_error}")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_payload(
    payload: object,
    *,
    question: QuestionSpec,
    valid_block_ids: set[str],
) -> QuestionAssessment:
    if not isinstance(payload, dict):
        raise ValueError("decision must be an object")
    decision = payload.get("decision")
    if decision not in MODEL_STATES:
        raise ValueError(f"unknown decision {decision!r}")
    state = str(decision)
    needs_missing = state == DECISION_PARTLY_ANSWERED

    statement = str(payload.get("statement") or "").strip()
    if not statement:
        raise ValueError("every decision must carry a statement")

    result = question.assessment(state)  # type: ignore[arg-type]
    result.statement = statement

    missing = str(payload.get("missing") or "").strip()
    if needs_missing and not missing:
        raise ValueError(
            "a partial answer must name what is still not stated, because that "
            "sentence is the only account of what the question leaves open"
        )
    if missing and not needs_missing:
        raise ValueError(
            f"{state} cannot carry a `missing` note: it is either fully answered or "
            "not addressed at all"
        )
    result.missing = missing

    block_ids = list(dict.fromkeys(_string_list(payload.get("block_ids"))))
    if state != DECISION_NOT_FOUND:
        if not block_ids:
            raise ValueError("answered from a document but cited no block")
        unknown = [b for b in block_ids if b not in valid_block_ids]
        if unknown:
            raise ValueError(f"cited block(s) that were not supplied: {unknown}")
        result.cited_block_ids = block_ids
    elif block_ids:
        raise ValueError("not_found cannot cite evidence")
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _format_blocks(blocks: list[ContentBlock]) -> str:
    if not blocks:
        return "(none)"
    return "\n\n".join(_format_block(block) for block in blocks)


def _format_block(block: ContentBlock) -> str:
    headings = " > ".join(block.heading_stack) if block.heading_stack else "none"
    extraction = extraction_context(block.structural_meta)
    metadata = f" | {extraction}" if extraction else ""
    return (
        f"[{block.id} | {block.doc_id} | {block.block_type} | "
        f"headings: {headings}{metadata}]\n{block.content}"
    )


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]
