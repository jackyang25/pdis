"""Ask, for one gate question, whether the supplied material answers it.

One schema-bound call per question. The decision is a single three-value enum
rather than a state plus a separate source field, because those two would need a
cross-field rule the schema cannot express — nothing stops a model returning
"absent" beside a cited block. One enum makes an incoherent answer unrepresentable
instead of merely invalid.

    answered_from_document   the documents state it; cite the blocks
    answered_from_context    a supplied context item states it; name which
    not_found                nothing supplied answers it

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
DECISION_FROM_CONTEXT = "answered_from_context"
DECISION_NOT_FOUND = "not_found"

_SCOPE_BOUNDARY = """Scope boundary:
- You are deciding only whether the supplied material ANSWERS the question. Do not
  judge how well the documents are written, whether they follow a template, or
  whether their targets are realistic. Those are other tools' jobs and a verdict
  here would contradict them.
- Do not answer the question yourself from your own knowledge. A question is
  answered only when the supplied material answers it.
- Partial is not answered. If the material addresses the subject but leaves the
  question open, that is absent."""


def build_assessment_prompt(has_context: bool) -> str:
    """The system prompt for one question. Published through the prompt catalog."""
    decisions = [
        f"- {DECISION_FROM_DOCUMENT}: the supplied document blocks answer the "
        "question. Cite in `block_ids` every block you read to reach that.",
    ]
    if has_context:
        decisions.append(
            f"- {DECISION_FROM_CONTEXT}: the supplied context answers the question "
            "and the documents do not. Name the exact context item in "
            "`context_label`. Context is not chunked, so it has no block IDs."
        )
    decisions.append(
        f"- {DECISION_NOT_FOUND}: nothing supplied answers the question. Leave "
        "`block_ids` empty and `context_label` blank. This is the right answer for a "
        "question the supplied material was never going to contain — an operational "
        "check, or a matter of judgment — as much as for one it should have."
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

`statement` is one short factual sentence (max 25 words). When answered, say what
the material states. When absent, say what is missing. Describe the material; do
not instruct the reader, and do not restate the question."""


def assessment_schema(
    blocks: list[ContentBlock],
    context_items: list[ContextItem],
) -> dict[str, Any]:
    """The closed shape one decision must take.

    The enums are built from what was actually supplied, so an unusable answer
    cannot be returned in the first place: no context items means no context
    decision, and `block_ids` can only name blocks that exist.
    """
    decisions = [DECISION_FROM_DOCUMENT, DECISION_NOT_FOUND]
    labels = [item.label for item in context_items]
    if labels:
        decisions.insert(1, DECISION_FROM_CONTEXT)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "statement", "block_ids", "context_label"],
        "properties": {
            "decision": {"type": "string", "enum": decisions},
            "statement": {"type": "string"},
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

    The bank's `likely_in` hint is deliberately absent. Telling the model where the
    answer supposedly lives would let a guess steer the search, which is exactly what
    demoting that field to a tag was meant to stop.
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
    statement = str(payload.get("statement") or "").strip()
    if not statement:
        raise ValueError("every decision must carry a statement")

    # The bank's contribution comes from one place, so a field added to the question
    # spec reaches every state rather than only the assessed ones.
    base = question.assessment("not_found")
    base.statement = statement

    if decision == DECISION_NOT_FOUND:
        return base

    if decision == DECISION_FROM_DOCUMENT:
        block_ids = list(dict.fromkeys(_string_list(payload.get("block_ids"))))
        if not block_ids:
            raise ValueError("answered from a document but cited no block")
        unknown = [b for b in block_ids if b not in valid_block_ids]
        if unknown:
            raise ValueError(f"cited block(s) that were not supplied: {unknown}")
        base.state = "answered"
        base.source = "document"
        base.cited_block_ids = block_ids
        return base

    if decision == DECISION_FROM_CONTEXT:
        label = str(payload.get("context_label") or "").strip()
        if label not in valid_labels:
            raise ValueError(
                f"named context item {label!r}, which was not supplied"
            )
        base.state = "answered"
        base.source = "context"
        base.context_label = label
        return base

    raise ValueError(f"unknown decision {decision!r}")


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
