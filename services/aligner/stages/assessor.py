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

The schema offers only the comparison document's blocks, so a verdict cannot be
justified by citing the document that set the bar. That is the one guarantee worth
having here: "the candidate says X" always points into the candidate's own file.

The citation is a selected line range, not typed text: `shared.spans` copies the chosen
lines out of the block, so the sentence a reader sees underlined is the document's, never
the model's recollection of it.
"""

from __future__ import annotations

from typing import Any

from shared.ai import request_structured
from shared.spans import LINE_SPAN_JSON_INSTRUCTION, line_span_schema

from services.chunker import ContentBlock

from ..context import format_blocks, image_inputs, read_spans

from ..models import (
    ALIGNMENT_VERDICTS,
    AlignmentFinding,
    LLMClientProtocol,
    Requirement,
    VERDICTS_REQUIRING_CITATION,
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

What honouring a requirement means depends on the kind of document this is, and the
first line of the message tells you which one you are reading.

- A **profile** — an intervention or candidate target product profile — honours a
  requirement by STATING A VALUE that satisfies it. Committing to numbers is its job.
- A **plan** — an integrated product development plan — honours a commitment by
  CONTAINING THE WORK directed at it: a study, an activity, a milestone, a decision
  point. Saying how is its job, and restating the number is not. A plan that names the
  work honours the commitment even though it states no value of its own; a plan that
  repeats the number and schedules nothing does not.

Judge presence, never sufficiency. Whether stated work is enough to reach a target, or
whether a target is achievable at all, is not answerable from these two documents and
is not what you are being asked.

Verdicts:
- meets: this document honours the requirement — a profile by stating a value that
  satisfies it, a plan by carrying the work for it. Cite the blocks.
- exceeds: it honours the requirement beyond what was asked — sooner, cheaper, longer,
  broader, or more work than the commitment needs. Cite the lines.
- falls_short: it addresses the requirement and honours only part of it — a value below
  the bar, or work reaching only some of what was committed to. Cite the lines.
- not_comparable: it addresses the same subject but not in terms that can be measured
  against the requirement — a qualitative claim against a numeric bar, a different
  population, a different endpoint. Cite the lines. Use this rather than guessing:
  reporting `falls_short` here would assert this document is worse, which it does not
  say.
- not_addressed: nothing in this document speaks to the requirement. Leave `spans`
  and `statement` empty. This is the right answer for a requirement this document was
  never meant to carry as much as for one it should have.

Lineage is required, not optional. Every verdict except `not_addressed` MUST select the
exact source lines it was read from. A citation you cannot point at is worse than
reporting the requirement unaddressed. Select the narrowest range that carries the
answer: a table row rather than the whole table, one sentence rather than the paragraph
around it.

{LINE_SPAN_JSON_INSTRUCTION}

`statement` is the only sentence you write, and it is one short factual sentence (max
25 words) saying what this document does about the subject — the value a profile states,
or the work a plan carries.

Leave it empty on `not_addressed`. "This document states nothing about X" is the verdict
in a sentence, under a heading that already names X.

Describe the document. Do not instruct the reader, do not restate the requirement, and
do not name the distance between the two: the requirement is shown directly above your
sentence, so "24-month shelf life" against a bar of 36 months is the whole finding and
"24 months against the 36 required" only says the bar again.

Do not name the document either. Start with the subject, not with what kind of file this
is: "The optimistic dosing schedule is a single IM dose", never "The candidate states a
single IM dose". The reader is shown which document your sentence describes, on the same
line as your sentence, so the prefix is four words of chrome before every finding - and
it reads as a claim about the document when the fact is about the product."""


def assessment_schema(blocks: list[ContentBlock]) -> dict[str, Any]:
    """The closed shape one verdict must take.

    The block enum offers the **comparison** document and nothing else, which is how the
    direction of the comparison survives into the citation: the model cannot prove a
    candidate meets a bar by pointing at the document that set it.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "statement", "spans"],
        "properties": {
            "verdict": {"type": "string", "enum": list(ALIGNMENT_VERDICTS)},
            "statement": {"type": "string"},
            "spans": {
                "type": "array",
                "items": line_span_schema([block.id for block in blocks]),
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
        "Document blocks:\n" + format_blocks(blocks),
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

    first_error = "model returned no structured verdict"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior verdict failed the Aligner contract: "
                f"{first_error}. Select real [line:N] ranges inside the supplied "
                "blocks unless the requirement is not addressed at all."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="aligner_requirement_verdict",
            schema=schema,
            images=image_inputs(blocks) or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured verdict")
            return _parse_payload(
                payload,
                requirement=requirement,
                edge_id=edge_id,
                blocks=blocks,
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
    blocks: list[ContentBlock],
) -> AlignmentFinding:
    if not isinstance(payload, dict):
        raise ValueError("verdict must be an object")
    verdict = payload.get("verdict")
    if verdict not in ALIGNMENT_VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}")

    statement = str(payload.get("statement") or "").strip()
    # Silence has nothing to describe: the sentence would be the verdict again, under a
    # heading that already names the requirement. Every other verdict says what this
    # document does about it, which the verdict alone cannot.
    if verdict == "not_addressed":
        statement = ""
    elif not statement:
        raise ValueError(f"{verdict} must say what this document does about the subject")

    finding = requirement.finding(edge_id, verdict)  # type: ignore[arg-type]
    finding.statement = statement

    spans = read_spans(payload.get("spans"), blocks)
    if verdict in VERDICTS_REQUIRING_CITATION:
        if not spans:
            raise ValueError(
                f"{verdict} must select the source lines it was read from, inside the "
                "document being checked"
            )
    elif spans:
        raise ValueError(
            "not_addressed cannot cite a passage: it is a claim about the absence of one"
        )
    finding.comparison_spans = spans
    return finding
