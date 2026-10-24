"""Structural checks on a finished gate review.

Structural only, in the sense `AGENTS.md` requires: known IDs, membership, and the
agreement between a state and the evidence it claims. Nothing here re-reads prose
or re-decides a question. It authorizes model output; it does not replace review.

The check that matters most is completeness. Every question in the resolved bank
appears exactly once, so a run cannot quietly assess fewer questions than the gate
asks and still present a count. What the bank owns — which discipline holds a
question, its text, its requirement, and whether it applies to this run's class —
is checked against the bank, because those are the facts no model decides.
"""

from __future__ import annotations

from .models import (
    MODEL_STATES,
    QUESTION_STATES,
    GateConfig,
    GateReview,
)


def validate_result_contract(result: GateReview, config: GateConfig) -> GateReview:
    """Return the reviewed result, or raise with what is structurally wrong."""
    _gate_matches(result, config)
    _documents(result)
    _questions_are_complete(result, config)
    _bank_facts_are_the_banks(result, config)
    _evidence_agrees_with_state(result)
    return result


def _gate_matches(result: GateReview, config: GateConfig) -> None:
    if result.gate_id != config.gate_id:
        raise ValueError(
            f"result is for gate {result.gate_id!r} but was validated against "
            f"{config.gate_id!r}"
        )
    if not result.gate_label.strip():
        raise ValueError("a gate review must carry its gate label")
    if not result.intervention_class.strip():
        raise ValueError("a gate review must carry its intervention class")
    if not config.serves(result.intervention_class):
        raise ValueError(
            f"the {config.gate_label} bank is not written for "
            f"{result.intervention_class!r}; a review of it would be a review of nothing"
        )
    if result.bank_source.strip() != config.mirrors.strip():
        raise ValueError(
            "a gate review must carry the bank source its config declares, so the "
            "saved file states which version of the question bank produced it"
        )


def _documents(result: GateReview) -> None:
    if not result.documents:
        raise ValueError("a gate review must carry at least one document")
    doc_ids = [document.doc_id for document in result.documents]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("two documents share a doc_id")
    if any(not doc_id.strip() for doc_id in doc_ids):
        raise ValueError("every document must carry a non-empty doc_id")

    block_ids = [block.id for block in result.blocks]
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("two carried blocks share an id")
    known_docs = set(doc_ids)
    for block in result.blocks:
        if block.doc_id not in known_docs:
            raise ValueError(
                f"block {block.id} belongs to {block.doc_id!r}, which is not a "
                "document this review carries"
            )

    missing_docs = known_docs - {block.doc_id for block in result.blocks}
    if missing_docs:
        raise ValueError(f"documents carry no readable blocks: {sorted(missing_docs)}")


def _questions_are_complete(result: GateReview, config: GateConfig) -> None:
    expected = [question.id for _, question in config.questions()]
    reported = [item.id for item in result.assessments()]
    if len(reported) != len(set(reported)):
        raise ValueError("a question appears twice in the review")

    missing = [question_id for question_id in expected if question_id not in set(reported)]
    if missing:
        raise ValueError(
            f"{len(missing)} question(s) the gate asks are absent from the review, "
            f"starting with {missing[0]}. The denominator cannot shrink."
        )
    extra = sorted(set(reported) - set(expected))
    if extra:
        raise ValueError(
            f"the review reports question(s) the gate does not ask: {extra}"
        )

    declared = {discipline.id for discipline in config.disciplines}
    for discipline in result.disciplines:
        if discipline.id not in declared:
            raise ValueError(
                f"discipline {discipline.id!r} is not declared by this gate's bank"
            )
        if not discipline.label.strip():
            raise ValueError(f"discipline {discipline.id!r} carries no label")


def _bank_facts_are_the_banks(result: GateReview, config: GateConfig) -> None:
    """Discipline, text, requirement and applicability come from the bank alone."""
    placed = [
        (discipline.id, [item.id for item in discipline.questions])
        for discipline in result.disciplines
    ]
    authored = [
        (discipline.id, [question.id for question in discipline.questions])
        for discipline in config.disciplines
    ]
    if placed != authored:
        raise ValueError(
            "questions must sit under the discipline that owns them, in bank order"
        )

    specs = {question.id: question for _, question in config.questions()}
    for item in result.assessments():
        question = specs[item.id]
        if item.text != question.text:
            raise ValueError(f"{item.id}: question text differs from the bank")
        if item.requirement != question.requirement:
            raise ValueError(f"{item.id}: requirement differs from the bank")
        applies = question.applies(result.intervention_class)
        if item.state == "not_applicable" and applies:
            raise ValueError(
                f"{item.id}: marked not_applicable, but the question applies to this run"
            )
        if item.state != "not_applicable" and not applies:
            raise ValueError(
                f"{item.id}: the question text does not apply to "
                f"{result.intervention_class}, so it cannot carry an assessment"
            )


def _evidence_agrees_with_state(result: GateReview) -> None:
    known_blocks = {block.id for block in result.blocks}

    for item in result.assessments():
        if item.state not in QUESTION_STATES:
            raise ValueError(f"{item.id}: unknown state {item.state!r}")
        if not item.text.strip():
            raise ValueError(f"{item.id}: a question must carry its text")

        # `missing` belongs to exactly one state. Anywhere else it would be an account
        # of a gap on a question that either has none or is entirely one.
        if item.state == "partly_answered":
            if not item.missing.strip():
                raise ValueError(
                    f"{item.id}: a partial answer must name what is still not stated"
                )
        elif item.missing:
            raise ValueError(
                f"{item.id}: state {item.state} cannot carry a `missing` note"
            )

        # Every model decision says what the material holds, `not_found` included; the
        # one state no model reached says nothing.
        if item.state in MODEL_STATES and not item.statement.strip():
            raise ValueError(f"{item.id}: a {item.state} question must carry a statement")
        if item.state == "not_applicable" and item.statement:
            raise ValueError(
                f"{item.id}: the question text excluded this run, so no model "
                "read it and there is nothing for it to have observed"
            )

        if item.state not in ("answered", "partly_answered"):
            if item.cited_block_ids:
                raise ValueError(
                    f"{item.id}: state {item.state} cannot cite evidence"
                )
            continue

        if not item.cited_block_ids:
            raise ValueError(f"{item.id}: answered but cites no block")
        unknown = [b for b in item.cited_block_ids if b not in known_blocks]
        if unknown:
            raise ValueError(f"{item.id}: cites unknown block(s) {unknown}")
        if len(set(item.cited_block_ids)) != len(item.cited_block_ids):
            raise ValueError(f"{item.id}: cites the same block twice")
