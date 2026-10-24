"""Independent, non-authoritative triage for document numeric proposals.

One request per proposal over the whole retained document, so the document and its
visuals lead every request and the proposal follows them. A review that stays invalid
after one retry, is refused, or whose provider fails leaves the proposal
``unavailable`` with the failure's code; the human decision is unaffected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, replace

from services.chunker import ContentBlock
from shared.ai import RECORDABLE_FAILURES, Effort, FailureCode, ModelTask, failure_code
from shared.batching import fixed_batches, map_ordered
from shared.request_budget import check_request
from shared.source_blocks import image_inputs

from ..ai import request_validated
from ..ai_contracts import target_review_batch
from ..context import limit_document_context, render_document_context
from ..models import Attribute, LLMClientProtocol, QuantitativeLedger, QuantitativeTarget
from ..prompt_primitives import (
    ATOMIC_TARGET_PRIMITIVE,
    COMPARATOR_POLICY_PRIMITIVE,
    SEMANTIC_DIMENSIONS_PRIMITIVE,
)


#: Reasoning counts against the budget; the reviewer reads the whole document.
MAX_TOKENS = 16000
# Per-item scope: one verification decision per proposed target, so an
# unrelated proposal can never sit in this decision's prompt.
TARGETS_PER_REQUEST = 1
#: The reasoning tier: this is the independent check on a number before it shapes
#: retrieval and statistics. Low effort, because the cited passage decides most
#: proposals and the run waits on one call per target.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
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
        "fields without becoming duplicate targets. Check the direct-comparator contract against "
        "the shared comparison policy: flag value/role leakage into matching rules, unsupported "
        "scope widening, or unknown required scope. Name the offending dimension and rule; do not "
        "silently repair it or confirm a correct number with an unsound contract.\n\n"
        "Verify the numeric expression's value, comparator, unit, and threshold/optimal role "
        "against the cited text, not just the proposal label. Do not repair an incorrect "
        "expression in your answer: identify the mismatch for human review.\n\n"
        "OUTPUT CONTRACT\n"
        "Review every supplied target ID exactly once. Give each decision one short, "
        "document-specific reason naming the decisive source fact. For a flag, name exactly "
        "what is ambiguous or what mapping needs checking; do not merely say 'review manually'. "
        "The reason is read by a reviewer beside the document, so write it in plain words: name a "
        "dimension as the thing it is (the dosing regimen, the statistic) and never in the "
        "`name=value` notation used above to show you the contract. "
        "Return only the schema-bound response."
    )


def prefill_target_review(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[Attribute], QuantitativeLedger]:
    """Recommend decisions without creating a second target interpretation.

    The verifier can select only existing target IDs and a closed decision. It
    cannot rewrite expressions, semantics, field links, or provenance. Clear
    recommendations prefill the client-held review; ambiguity remains pending.
    """
    if not ledger.targets:
        return attributes, ledger
    attributes_by_name = {attribute.name: attribute for attribute in attributes}
    prompt = build_review_system_prompt()
    proposals = {
        target.id: _proposal(target, attributes_by_name) for target in ledger.targets
    }
    document = (
        "COMPLETE UPLOADED DOCUMENT FOR DISAMBIGUATION\n"
        + limit_document_context(render_document_context(blocks))
    )
    images = image_inputs(blocks) or None
    # Every request repeats the document and its visuals, so an oversized one is
    # refused once, here, rather than by the provider once per target.
    check_request("Scout's target review", text=document, images=images)
    batches = fixed_batches([target.id for target in ledger.targets], TARGETS_PER_REQUEST)

    def review_batch(batch_ids: list[str]) -> dict[str, _Recommendation]:
        try:
            return request_validated(
                llm_client,
                target_review_batch(batch_ids),
                prompt,
                document,
                max_tokens=MAX_TOKENS,
                images=images,
                trailing_text=(
                    "\n\nPROPOSALS TO REVIEW\n"
                    + "\n\n".join(proposals[target_id] for target_id in batch_ids)
                ),
                task=TASK,
                effort=EFFORT,
                parse=lambda raw: _validated_decisions(raw, batch_ids),
                failure="Independent target review failed",
            )
        except RECORDABLE_FAILURES as exc:
            logger.warning(
                "Document-target AI prefill unavailable for %d proposal(s): %s",
                len(batch_ids),
                exc,
            )
            code = failure_code(exc)
            return {
                target_id: ("unavailable", str(exc), code) for target_id in batch_ids
            }

    if progress:
        progress(0, len(batches))
    by_id: dict[str, _Recommendation] = {}
    for decisions in map_ordered(
        batches, review_batch, workers=MAX_REVIEW_WORKERS, on_progress=progress,
    ):
        by_id.update(decisions)
    return _apply_recommendations(attributes, ledger, by_id)


#: decision, reason, failure code ("" for a model decision).
_Recommendation = tuple[str, str, FailureCode | str]


def _proposal(target: QuantitativeTarget, attributes_by_name: dict[str, Attribute]) -> str:
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
    return "\n".join(
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
            "Numeric expression: " + json.dumps(asdict(target.expression), ensure_ascii=False),
            f"Target role: {target.role}",
            "Exact cited passages: " + " | ".join(
                span.quote for span in target.provenance_spans
            ),
            f"Mapped meaning: {semantics}",
            f"Direct-comparator contract: {comparison}",
        )
    )


def _validated_decisions(raw: object, batch_ids: list[str]) -> dict[str, _Recommendation]:
    """One closed decision with a reason for every requested target, or a retry."""
    decisions: dict[str, _Recommendation] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("target_id", "")).strip()
        decision = str(item.get("decision", "")).strip().lower()
        reason = " ".join(str(item.get("reason", "")).split())
        if (
            target_id in batch_ids
            and target_id not in decisions
            and decision in {"confirm", "exclude", "flag"}
            and reason
        ):
            decisions[target_id] = (decision, reason, "")
    missing = [target_id for target_id in batch_ids if target_id not in decisions]
    if missing:
        raise ValueError(
            "no complete decision with a reason for target(s) " + ", ".join(missing)
        )
    return decisions


def _apply_recommendations(
    attributes: list[Attribute],
    ledger: QuantitativeLedger,
    by_id: dict[str, _Recommendation],
) -> tuple[list[Attribute], QuantitativeLedger]:
    reviewed_targets: list[QuantitativeTarget] = []
    for target in ledger.targets:
        decision, reason, code = by_id[target.id]
        reviewed_targets.append(replace(
            target,
            ai_recommendation=decision,
            ai_review_reason=reason,
            ai_review_failure_code=code,
            # AI triage is a recommendation, not the human decision boundary.
            # This matches evidence review: explicit UI acceptance is the only
            # operation that changes a review item to approved or rejected.
            review_status="needs_review",
            id=target.id,
        ))

    return attributes, replace(ledger, targets=reviewed_targets)
