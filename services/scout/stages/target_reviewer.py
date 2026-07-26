"""Independent, non-authoritative triage for document numeric proposals."""

from __future__ import annotations

import logging
from dataclasses import replace

from services.chunker import ContentBlock

from ..ai import request_structured
from ..ai_contracts import target_review_batch
from ..context import render_document_context
from ..models import Attribute, LLMClientProtocol, QuantitativeLedger, QuantitativeTarget


MAX_TOKENS = 5000
MAX_TARGETS_PER_REVIEW = 16
logger = logging.getLogger(__name__)


def prefill_target_review(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol | None,
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Recommend decisions without creating a second target interpretation.

    The verifier can select only existing target IDs and a closed decision. It
    cannot rewrite expressions, semantics, ownership, or provenance. Clear
    recommendations prefill the client-held review; ambiguity remains pending.
    """
    if not ledger.targets:
        return attributes, ledger
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    prompt = (
        "You independently verify existing document numeric-target proposals. "
        "You cannot create, rewrite, merge, or reassign targets. Decide confirm only when "
        "the cited document language makes the proposed number an intended requirement, "
        "constraint, threshold, optimum, or explicitly defined operating/use-case target "
        "for its canonical field and the displayed semantic mapping is faithful. Decide "
        "exclude when the number is merely epidemiology, background evidence, rationale, "
        "an example, a citation, a rejected alternative, or another field's fact. Decide "
        "flag whenever intent or mapping is genuinely ambiguous. Review every supplied target ID "
        "exactly once. Give one short, document-specific reason. Return only schema JSON."
    )
    proposals: dict[str, str] = {}
    for target in ledger.targets:
        attribute = attributes_by_name[target.attribute_ref]
        semantics = "; ".join(
            f"{name}={slot.value or slot.other or slot.state}"
            for name, slot in target.semantic_profile.items()
            if name in target.comparison_dimensions
        )
        proposals[target.id] = "\n".join(
            (
                f"[target:{target.id}]",
                f"Canonical field: {attribute.name} — {attribute.description}",
                f"Canonical field binding: {attribute.document_target}",
                f"Proposed target: {target.label}",
                f"Exact cited passage: {target.quote}",
                f"Mapped meaning: {semantics}",
            )
        )
    document = render_document_context(blocks)
    images = [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ] or None
    by_id: dict[str, tuple[str, str]] = {}
    target_ids = [target.id for target in ledger.targets]
    if llm_client is None:
        return _apply_recommendations(
            attributes,
            ledger,
            {},
            missing_reason=(
                "Anthropic target verification is not configured; review this proposal manually."
            ),
        )
    for offset in range(0, len(target_ids), MAX_TARGETS_PER_REVIEW):
        batch_ids = target_ids[offset : offset + MAX_TARGETS_PER_REVIEW]
        message = (
            "Review these existing proposals:\n\n"
            + "\n\n".join(proposals[target_id] for target_id in batch_ids)
            + "\n\nComplete uploaded document for disambiguation:\n"
            + document
        )
        try:
            raw = request_structured(
                llm_client,
                target_review_batch(batch_ids),
                prompt,
                message,
                max_tokens=MAX_TOKENS,
                images=images,
                task="reasoning",
            )
        except Exception as exc:  # Independent triage must degrade to manual review.
            logger.warning(
                "Document-target AI prefill failed for %d proposal(s); flagging them: %s",
                len(batch_ids),
                exc,
            )
            raw = None
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                target_id = str(item.get("target_id", "")).strip()
                decision = str(item.get("decision", "")).strip().lower()
                reason = " ".join(str(item.get("reason", "")).split())
                if (
                    target_id in batch_ids
                    and target_id not in by_id
                    and decision in {"confirm", "exclude", "flag"}
                    and reason
                ):
                    by_id[target_id] = (decision, reason)

    return _apply_recommendations(attributes, ledger, by_id)


def _apply_recommendations(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    by_id: dict[str, tuple[str, str]],
    *,
    missing_reason: str = "Independent AI verification did not return one complete decision.",
) -> tuple[list[Attribute], QuantitativeLedger]:
    reviewed_targets: list[QuantitativeTarget] = []
    for target in ledger.targets:
        decision, reason = by_id.get(
            target.id,
            ("flag", missing_reason),
        )
        status = {
            "confirm": "approved",
            "exclude": "rejected",
            "flag": "needs_review",
        }[decision]
        reviewed_targets.append(replace(
            target,
            ai_recommendation=decision,
            ai_review_reason=reason,
            review_status=status,
            id=target.id,
        ))

    targets_by_id = {target.id: target for target in reviewed_targets}
    reviewed_attributes = [
        replace(
            attribute,
            quantitative_targets=[
                targets_by_id[target.id] for target in attribute.quantitative_targets
            ],
        )
        for attribute in attributes
    ]
    return reviewed_attributes, replace(ledger, targets=reviewed_targets)
