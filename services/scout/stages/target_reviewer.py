"""Independent, non-authoritative triage for document numeric proposals."""

from __future__ import annotations

import logging
from dataclasses import replace

from services.chunker import ContentBlock

from ..ai import request_structured
from shared.batching import fixed_batches, map_ordered
from ..ai_contracts import target_review_batch
from ..context import render_document_context
from ..models import Attribute, LLMClientProtocol, QuantitativeLedger, QuantitativeTarget
from ..prompt_primitives import (
    ATOMIC_TARGET_PRIMITIVE,
    COMPARATOR_POLICY_PRIMITIVE,
    SEMANTIC_DIMENSIONS_PRIMITIVE,
)


MAX_TOKENS = 5000
# Per-item scope: one verification decision per proposed target, so an
# unrelated proposal can never sit in this decision's prompt.
TARGETS_PER_REQUEST = 1
MAX_REVIEW_WORKERS = 4
logger = logging.getLogger(__name__)


def build_review_system_prompt() -> str:
    """Instructions sent when triaging document numeric proposals."""
    return (
        "ROLE\n"
        "You independently review existing document numeric-target proposals. You recommend "
        "decisions; you cannot create, rewrite, merge, or reassign targets, semantic mappings, "
        "field links, citations, or provenance.\n\n"
        "INPUT AUTHORITY\n"
        "Review only the supplied immutable proposals and their exact cited document passages. "
        "The complete document may disambiguate a proposal but may not create a new one.\n\n"
        "SHARED PRIMITIVES\n"
        f"{ATOMIC_TARGET_PRIMITIVE}\n\n"
        f"{SEMANTIC_DIMENSIONS_PRIMITIVE}\n\n"
        f"{COMPARATOR_POLICY_PRIMITIVE}\n\n"
        "DECISION PROCEDURE\n"
        "Confirm only when the cited document language makes the proposed number an intended "
        "requirement, constraint, threshold, optimum, or explicitly defined operating or use-case "
        "target, and the displayed semantic mapping and typed field links are faithful. Exclude "
        "when the number is epidemiology, background evidence, rationale, an example, a citation, "
        "or a rejected alternative. Flag genuine ambiguity in intent, mapping, or source support. "
        "Fields are product views, not target owners: one proposal may define or constrain multiple "
        "fields without becoming duplicate targets. Also review the direct-comparator contract: "
        "exact means the same entity-level meaning is required, compatible permits different named "
        "entities within its stated scope, unconstrained does not control admission, and unknown "
        "must remain flagged. Do not require exact product identity merely because the document "
        "names its candidate; comparator cohorts normally contain different products in a declared "
        "class or use. Use the complete document only to disambiguate "
        "the supplied proposals; do not extract new ones.\n\n"
        "OUTPUT CONTRACT\n"
        "Review every supplied target ID exactly once. Give each decision one short, "
        "document-specific reason. Return only the schema-bound response."
    )


def prefill_target_review(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol | None,
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Recommend decisions without creating a second target interpretation.

    The verifier can select only existing target IDs and a closed decision. It
    cannot rewrite expressions, semantics, field links, or provenance. Clear
    recommendations prefill the client-held review; ambiguity remains pending.
    """
    if not ledger.targets:
        return attributes, ledger
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    prompt = (
        build_review_system_prompt()
    )
    proposals: dict[str, str] = {}
    for target in ledger.targets:
        linked_fields = [
            attributes_by_name[link.attribute_ref]
            for link in target.field_links
            if link.attribute_ref in attributes_by_name
        ]
        semantics = "; ".join(
            f"{name}={slot.value or slot.other or slot.state}"
            for name, slot in target.semantic_profile.items()
            if name in target.comparison_dimensions
        )
        comparison = "; ".join(
            f"{name}={rule.mode}({rule.scope or rule.reason})"
            for name, rule in target.comparison_contract.items()
        )
        proposals[target.id] = "\n".join(
            (
                f"[target:{target.id}]",
                "Field links: " + "; ".join(
                    f"{link.attribute_ref} ({link.relation}: {link.reason})"
                    for link in target.field_links
                ),
                "Linked field definitions: " + "; ".join(
                    f"{attribute.name} — {attribute.description}"
                    for attribute in linked_fields
                ),
                "Linked canonical bindings: " + " | ".join(
                    attribute.document_target for attribute in linked_fields
                ),
                f"Proposed target: {target.label}",
                "Exact cited passages: " + " | ".join(
                    span.quote for span in target.provenance_spans
                ),
                f"Mapped meaning: {semantics}",
                f"Direct-comparator contract: {comparison}",
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
                "Independent target verification is not configured; review this proposal manually."
            ),
        )

    batches = fixed_batches(target_ids, TARGETS_PER_REQUEST)

    def review_batch(batch_ids: list[str]) -> object | None:
        message = (
            "PROPOSALS TO REVIEW\n"
            + "\n\n".join(proposals[target_id] for target_id in batch_ids)
            + "\n\nCOMPLETE UPLOADED DOCUMENT FOR DISAMBIGUATION\n"
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
            return None
        return raw

    responses = map_ordered(batches, review_batch, workers=MAX_REVIEW_WORKERS)

    for batch_ids, raw in zip(batches, responses):
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
        reviewed_targets.append(replace(
            target,
            ai_recommendation=decision,
            ai_review_reason=reason,
            # AI triage is a recommendation, not the human decision boundary.
            # This matches evidence review: explicit UI acceptance is the only
            # operation that changes a review item to approved or rejected.
            review_status="needs_review",
            id=target.id,
        ))

    return attributes, replace(ledger, targets=reviewed_targets)
