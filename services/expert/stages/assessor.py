"""Ask, for one gate question, whether the supplied material answers it.

One schema-bound call per question. The decision is a single three-value enum
rather than a state plus a separate source field, because those two would need a
cross-field rule the schema cannot express — nothing stops a model returning
"absent" beside a cited block. One enum makes an incoherent answer unrepresentable
instead of merely invalid.

    answered_from_document   the documents answer it fully; cite the blocks
    partly_from_document     the documents answer part of it; cite, and name the rest
    answered_from_context    a supplied context item answers it fully; name which
    partly_from_context      a context item answers part of it; name which, and the rest
    not_found                nothing supplied addresses it

Completeness and source are independent, so the enum is their cross product rather
than two fields. Five values reads wide, but the alternative is a rule no schema can
express — nothing would stop "partly" arriving with no account of what is missing. The
context variants are omitted entirely when no context was supplied, so a run without it
sees three.

`answered_from_context` is offered only when context items were actually supplied,
so a model cannot attribute an answer to a source that does not exist. Both
citation forms are membership-checked, which is the same guarantee and the same
limit: you cannot prove a model read something, only that what it named exists.
"""

from __future__ import annotations

from typing import Any

from shared.ai import request_structured

from services.chunker import ContentBlock

from ..models import (
    ContextItem,
    LLMClientProtocol,
    QuestionAssessment,
    QuestionSpec,
)

# One question per request. An unrelated question in this prompt would influence
# the decision, and batch composition would shift between runs. Throughput comes
# from fan-out in the pipeline, never from packing questions together.
QUESTIONS_PER_REQUEST = 1

DECISION_FROM_DOCUMENT = "answered_from_document"
DECISION_PARTLY_FROM_DOCUMENT = "partly_from_document"
DECISION_FROM_CONTEXT = "answered_from_context"
DECISION_PARTLY_FROM_CONTEXT = "partly_from_context"
DECISION_NOT_FOUND = "not_found"

#: How each decision maps onto the published state and source. One table rather than a
#: branch per decision, so adding a decision is one row and nothing downstream reads
#: the decision vocabulary at all.
_DECISIONS: dict[str, tuple[str, str | None, bool]] = {
    # decision: (state, source, requires `missing`)
    DECISION_FROM_DOCUMENT: ("answered", "document", False),
    DECISION_PARTLY_FROM_DOCUMENT: ("partly_answered", "document", True),
    DECISION_FROM_CONTEXT: ("answered", "context", False),
    DECISION_PARTLY_FROM_CONTEXT: ("partly_answered", "context", True),
    DECISION_NOT_FOUND: ("not_found", None, False),
}

_SCOPE_BOUNDARY = """Scope boundary:
- You are deciding only whether the supplied material ANSWERS the question. Do not
  judge how well the documents are written, whether they follow a template, or
  whether their targets are realistic. Those are other tools' jobs and a verdict
  here would contradict them.
- Do not answer the question yourself from your own knowledge. A question is
  answered only when the supplied material answers it.
- These questions are compound: most ask three to five things in one sentence. Judge
  them clause by clause. Every clause answered is answered; some answered is partly;
  none is not found. Do not round a partial up or down."""


def build_assessment_prompt(has_context: bool) -> str:
    """The system prompt for one question. Published through the prompt catalog."""
    decisions = [
        f"- {DECISION_FROM_DOCUMENT}: the supplied document blocks answer every part "
        "of the question. Cite in `block_ids` every block you read to reach that.",
        f"- {DECISION_PARTLY_FROM_DOCUMENT}: the documents answer some parts and leave "
        "others open. Cite the blocks, and put in `missing` one short sentence naming "
        "exactly what is still not stated.",
    ]
    if has_context:
        decisions.extend([
            f"- {DECISION_FROM_CONTEXT}: the supplied context answers every part and "
            "the documents do not. Name the exact context item in `context_label`. "
            "Context is not chunked, so it has no block IDs.",
            f"- {DECISION_PARTLY_FROM_CONTEXT}: the supplied context answers some "
            "parts. Name the item, and put the rest in `missing`.",
        ])
    decisions.append(
        f"- {DECISION_NOT_FOUND}: nothing supplied addresses the question at all. "
        "Leave `block_ids` empty and `context_label` and `missing` blank. This is the "
        "right answer for a question the supplied material was never going to contain "
        "— an operational check, or a matter of judgment — as much as for one it "
        "should have."
    )
    preference = (
        "\n\nPrefer the documents. When both a document and a context item answer "
        "the question, choose the document, because only that answer can be checked."
        if has_context
        else ""
    )
    return f"""You are triaging one stage-gate review question against a set of product-development documents.

{_SCOPE_BOUNDARY}

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Decisions:
{chr(10).join(decisions)}{preference}

Lineage is required, not optional. `{DECISION_FROM_DOCUMENT}` MUST cite the exact
supplied block IDs it was read from. A citation you cannot point at is worse than
reporting the question unanswered.

`statement` is one short factual sentence (max 25 words) saying what the material
states, or that it states nothing on the subject. When the answer came from a context item
that shows page markers, name the page in it — that is the nearest thing to a citation
context can carry, and a reader who has the file can then find it.

`missing` is one short sentence (max 25 words) naming only what is still not stated,
on a partial answer and nowhere else. It is read as an instruction to whoever wrote the
document, so name the thing, not its absence: "Zone IVb stability data and the VVM
category" rather than "the document does not say".

Describe the material; do not instruct the reader, and do not restate the question."""


def assessment_schema(
    blocks: list[ContentBlock],
    context_items: list[ContextItem],
) -> dict[str, Any]:
    """The closed shape one decision must take.

    The enums are built from what was actually supplied, so an unusable answer
    cannot be returned in the first place: no context items means no context
    decision, and `block_ids` can only name blocks that exist.
    """
    labels = [item.label for item in context_items]
    decisions = [DECISION_FROM_DOCUMENT, DECISION_PARTLY_FROM_DOCUMENT]
    if labels:
        decisions += [DECISION_FROM_CONTEXT, DECISION_PARTLY_FROM_CONTEXT]
    decisions.append(DECISION_NOT_FOUND)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision",
            "statement",
            "missing",
            "block_ids",
            "context_label",
        ],
        "properties": {
            "decision": {"type": "string", "enum": decisions},
            "statement": {"type": "string"},
            # Always present, blank unless the decision is a partial. A conditional
            # requirement is the one thing this schema cannot express, so the decision
            # carries the condition and code checks the pairing.
            "missing": {"type": "string"},
            "block_ids": {
                "type": "array",
                "items": {"type": "string", "enum": [block.id for block in blocks]},
            },
            # "" is a member so absence is representable without a nullable type.
            "context_label": {"type": "string", "enum": [*labels, ""]},
        },
    }


def build_user_message(
    question: QuestionSpec,
    blocks: list[ContentBlock],
    context_items: list[ContextItem],
) -> str:
    """The supplied material first, the question last.

    Order matters for cost, not for reading. Every question in a run receives the same
    documents and the same context, so putting them first makes them a prompt prefix a
    provider can cache: the expensive half is paid for once instead of once per
    question. With the question first — as this was — every call had a different first
    line and shared nothing.

    The bank's `requirement` is deliberately absent. Whether a gate requires this now or
    expects it to be forming is a fact about the review, not about the documents, and a
    model told a question is only "anticipatory" would read the material less carefully
    for it. The same triage runs either way; the distinction is for the reader.
    """
    parts = ["Supplied document blocks:\n" + _format_blocks(blocks)]
    for item in context_items:
        parts.append(f"Supplied context — {item.label}:\n{item.text.strip()}")
    parts.append(f"Question ({question.id}):\n{question.text}")
    return "\n\n".join(parts)


def assess_question(
    question: QuestionSpec,
    *,
    blocks: list[ContentBlock],
    context_items: list[ContextItem],
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> QuestionAssessment:
    """One decision about one question, with its lineage validated."""
    system_prompt = build_assessment_prompt(bool(context_items))
    user_message = build_user_message(question, blocks, context_items)
    schema = assessment_schema(blocks, context_items)
    images = _image_inputs(blocks)
    valid_block_ids = {block.id for block in blocks}
    valid_labels = {item.label for item in context_items}

    first_error = "model returned no structured decision"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior decision failed the Expert contract: "
                f"{first_error}. Cite the exact supplied block IDs when answering "
                "from a document, name a supplied context item when answering from "
                "context, and cite nothing when the question is unanswered."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="expert_question_triage",
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
                valid_labels=valid_labels,
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(f"Expert could not triage {question.id}: {first_error}")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_payload(
    payload: object,
    *,
    question: QuestionSpec,
    valid_block_ids: set[str],
    valid_labels: set[str],
) -> QuestionAssessment:
    if not isinstance(payload, dict):
        raise ValueError("decision must be an object")
    decision = payload.get("decision")
    if decision not in _DECISIONS:
        raise ValueError(f"unknown decision {decision!r}")
    state, source, needs_missing = _DECISIONS[str(decision)]

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

    if source == "document":
        block_ids = list(dict.fromkeys(_string_list(payload.get("block_ids"))))
        if not block_ids:
            raise ValueError("answered from a document but cited no block")
        unknown = [b for b in block_ids if b not in valid_block_ids]
        if unknown:
            raise ValueError(f"cited block(s) that were not supplied: {unknown}")
        result.source = "document"
        result.cited_block_ids = block_ids
        return result

    if source == "context":
        label = str(payload.get("context_label") or "").strip()
        if label not in valid_labels:
            raise ValueError(f"named context item {label!r}, which was not supplied")
        result.source = "context"
        result.context_label = label
        return result

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
    return (
        f"[{block.id} | {block.source_type or block.doc_id} | {block.block_type} | "
        f"headings: {headings}]\n{block.content}"
    )


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]
