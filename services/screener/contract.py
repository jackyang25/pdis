"""Structural checks on a finished gate review.

Structural only, in the sense `AGENTS.md` requires: known IDs, membership, and the
agreement between a state and the evidence it claims. Nothing here re-reads prose
or re-decides a question. It authorizes model output; it does not replace review.

The check that matters most is completeness. Every question in the resolved bank
appears exactly once, so a run cannot quietly assess fewer questions than the gate
asks and still present a count.
"""

from __future__ import annotations

from .models import (
    ANSWER_SOURCES,
    QUESTION_STATES,
    GateConfig,
    GateReview,
)


def validate_result_contract(result: GateReview, config: GateConfig) -> GateReview:
    """Return the reviewed result, or raise with what is structurally wrong."""
    _gate_matches(result, config)
    _documents(result)
    _questions_are_complete(result, config)
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
    if any(not document.source_type.strip() for document in result.documents):
        raise ValueError("every document must carry its source type")

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

    labels = result.context_labels
    if len(set(labels)) != len(labels):
        raise ValueError("two context items share a label")
    if any(not label.strip() for label in labels):
        raise ValueError("every context item must carry a label")


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


def _evidence_agrees_with_state(result: GateReview) -> None:
    known_blocks = {block.id for block in result.blocks}
    known_labels = set(result.context_labels)

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

        if item.state not in ("answered", "partly_answered"):
            if item.source is not None:
                raise ValueError(
                    f"{item.id}: state {item.state} cannot carry an answer source"
                )
            if item.cited_block_ids or item.context_label:
                raise ValueError(
                    f"{item.id}: state {item.state} cannot cite evidence"
                )
            if item.state == "not_applicable" and item.statement:
                raise ValueError(
                    f"{item.id}: the question text excluded this run, so no model "
                    "read it and there is nothing for it to have observed"
                )
            continue

        if item.source not in ANSWER_SOURCES:
            raise ValueError(f"{item.id}: an answered question must name its source")
        if not item.statement.strip():
            raise ValueError(f"{item.id}: an answered question must say what it found")

        if item.source == "document":
            if not item.cited_block_ids:
                raise ValueError(
                    f"{item.id}: answered from a document but cites no block"
                )
            unknown = [b for b in item.cited_block_ids if b not in known_blocks]
            if unknown:
                raise ValueError(f"{item.id}: cites unknown block(s) {unknown}")
            if len(set(item.cited_block_ids)) != len(item.cited_block_ids):
                raise ValueError(f"{item.id}: cites the same block twice")
            if item.context_label:
                raise ValueError(
                    f"{item.id}: answered from a document but also names a context "
                    "item; an answer has one source"
                )
            continue

        # source == "context": attribution without lineage, and it must be a label
        # the user actually supplied — the same membership guarantee a block ID
        # gives, since neither can be proven to have been read.
        if item.context_label not in known_labels:
            raise ValueError(
                f"{item.id}: names context item {item.context_label!r}, which was "
                "not supplied"
            )
        if item.cited_block_ids:
            raise ValueError(
                f"{item.id}: answered from supplied context cannot cite a block, "
                "because transient input is never chunked"
            )
