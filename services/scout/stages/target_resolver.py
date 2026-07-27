"""Bind a canonical investigation-unit definition to its document target.

Dynamic providers already extract the target and its exact blocks. Fixed
providers supply only a stable definition, so this stage locates the matching
document statement. Both paths leave this stage with the same resolved
``Attribute`` contract.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from ..ai import request_structured
from ..ai_contracts import target_binding_batch
from ..context import (
    LINE_SPAN_JSON_INSTRUCTION,
    chunk_document_context,
    document_block_ids,
    render_line_addressable_context,
    rendered_block_texts,
    selected_source_lines,
)
from ..models import (
    Attribute,
    DocumentSpan,
    LLMClientProtocol,
    parse_evidence_entities,
)

DEFAULT_MAX_TOKENS = 32000
FIELD_BATCH_SIZE = 6
FIELD_BATCH_WORKERS = 6
logger = logging.getLogger(__name__)


@dataclass
class _LedgerValidation:
    decisions: dict[str, Attribute]
    valid_refs: set[str]


@dataclass(frozen=True)
class _SpanValidation:
    span: DocumentSpan | None
    code: str
    reason: str


def resolve_document_targets(
    attributes: list[Attribute],
    document_context: str,
    llm_client: LLMClientProtocol,
    *,
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    progress_callback=None,
) -> list[Attribute]:
    """Bind fixed definitions into one canonical document-level ledger.

    Dynamic providers already return document-bound ``Attribute`` objects and
    pass through unchanged. Every bounded output request receives the complete
    catalog so one statement cannot acquire competing meanings in isolated
    per-field calls.
    """
    fixed = [attribute for attribute in attributes if not attribute.target_resolved]
    if not fixed:
        return attributes
    chunks = chunk_document_context(document_context)
    field_batches = [
        fixed[index:index + FIELD_BATCH_SIZE]
        for index in range(0, len(fixed), FIELD_BATCH_SIZE)
    ]
    tasks = [
        (chunk, batch)
        for chunk in chunks
        for batch in field_batches
    ]
    if progress_callback and tasks:
        progress_callback(completed=0, total=len(tasks))
    progress_lock = threading.Lock()
    progress_state = {"completed": 0}

    def resolve_batch(task: tuple[str, list[Attribute]]) -> dict[str, Attribute]:
        chunk, requested = task
        chunk_ids = document_block_ids(chunk)
        contract = target_binding_batch(
            sorted(chunk_ids),
            [attribute.name for attribute in requested],
        )
        parsed = request_structured(
            llm_client,
            contract,
            _ledger_system_prompt(fixed, requested),
            _ledger_user_message(chunk, requested),
            max_tokens=max_tokens,
            images=[
                image for image in (images or []) if image["block_id"] in chunk_ids
            ]
            or None,
        )
        validation = _validated_ledger(parsed, requested, chunk)
        missing = [
            attribute
            for attribute in requested
            if attribute.name not in validation.valid_refs
        ]
        if missing:
            retry_contract = target_binding_batch(
                sorted(chunk_ids),
                [attribute.name for attribute in missing],
            )
            retry_parsed = request_structured(
                llm_client,
                retry_contract,
                _ledger_system_prompt(fixed, missing, retry=True),
                _ledger_user_message(chunk, missing),
                max_tokens=max_tokens,
                images=[
                    image
                    for image in (images or [])
                    if image["block_id"] in chunk_ids
                ]
                or None,
            )
            retry = _validated_ledger(retry_parsed, missing, chunk)
            for attribute in missing:
                validation.decisions[attribute.name] = retry.decisions[attribute.name]
        return validation.decisions

    def resolve_and_report(task: tuple[str, list[Attribute]]) -> dict[str, Attribute]:
        decisions = resolve_batch(task)
        if progress_callback:
            with progress_lock:
                progress_state["completed"] += 1
                progress_callback(
                    completed=progress_state["completed"],
                    total=len(tasks),
                )
        return decisions

    workers = max(1, min(FIELD_BATCH_WORKERS, len(tasks))) if tasks else 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        ledgers = list(executor.map(resolve_and_report, tasks))
    bindings = _merge_ledgers(fixed, ledgers)
    return [bindings.get(attribute.name, attribute) for attribute in attributes]


def _merge_ledgers(
    attributes: list[Attribute],
    ledgers: list[dict[str, Attribute]],
) -> dict[str, Attribute]:
    merged: dict[str, Attribute] = {}
    for attribute in attributes:
        decisions = [
            ledger[attribute.name]
            for ledger in ledgers
            if attribute.name in ledger
        ]
        present = [decision for decision in decisions if decision.document_target]
        if present:
            spans = list(
                {
                    (span.quote, tuple(span.block_ids)): span
                    for decision in present
                    for span in decision.document_spans
                }.values()
            )
            merged[attribute.name] = replace(
                attribute,
                document_spans=spans,
                entities=list(
                    dict.fromkeys(
                        entity for decision in present for entity in decision.entities
                    )
                ),
                target_resolved=True,
                target_resolution_reason=(
                    "The document claim ledger resolved this field from exact spans."
                ),
            )
        else:
            resolved_absent = bool(decisions) and all(
                decision.target_resolved for decision in decisions
            )
            unresolved_reasons = list(
                dict.fromkeys(
                    decision.target_resolution_reason
                    for decision in decisions
                    if not decision.target_resolved
                    and decision.target_resolution_reason
                )
            )
            merged[attribute.name] = replace(
                attribute,
                document_target="",
                document_spans=[],
                block_ids=[],
                entities=[],
                target_resolved=resolved_absent,
                target_resolution_reason=(
                    "The complete document claim ledger found no directly stated target."
                    if resolved_absent
                    else "; ".join(unresolved_reasons)[:1000]
                    or "No complete validated decision was returned for this field."
                ),
            )
    return merged


def _validated_ledger(
    parsed: object,
    attributes: list[Attribute],
    document_context: str,
) -> _LedgerValidation:
    definitions = {attribute.name: attribute for attribute in attributes}
    source_blocks = rendered_block_texts(document_context)
    # Missing, duplicated, or invalid decisions remain explicitly unresolved.
    # One malformed field must not erase valid bindings for every other field.
    decisions: dict[str, Attribute] = {
        attribute.name: replace(
            attribute,
            document_target="",
            document_spans=[],
            block_ids=[],
            entities=[],
            target_resolved=False,
            target_resolution_reason=(
                "No unique validated document-claim decision was returned."
            ),
        )
        for attribute in attributes
    }
    if not isinstance(parsed, list):
        return _LedgerValidation(decisions=decisions, valid_refs=set())
    counts: dict[str, int] = {}
    for item in parsed:
        if isinstance(item, dict):
            attribute_ref = str(item.get("attribute_ref", "")).strip()
            if attribute_ref in definitions:
                counts[attribute_ref] = counts.get(attribute_ref, 0) + 1
    for attribute_ref, count in counts.items():
        if count > 1:
            decisions[attribute_ref] = replace(
                decisions[attribute_ref],
                target_resolution_reason=(
                    "The model returned duplicate decisions for this field."
                ),
            )
    valid_refs: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        attribute_ref = str(item.get("attribute_ref", "")).strip()
        status = str(item.get("status", "")).strip().lower()
        reason = " ".join(str(item.get("reason", "")).split())
        attribute = definitions.get(attribute_ref)
        if attribute is None or counts.get(attribute_ref) != 1:
            continue
        if status not in {"present", "absent", "uncertain"} or not reason:
            decisions[attribute_ref] = replace(
                decisions[attribute_ref],
                target_resolution_reason=(
                    "The returned decision had an invalid status or no reason."
                ),
            )
            continue
        raw_spans = item.get("spans")
        raw_spans = raw_spans if isinstance(raw_spans, list) else []
        if status != "present":
            raw_entities = item.get("entities")
            if raw_spans or (isinstance(raw_entities, list) and raw_entities):
                decisions[attribute_ref] = replace(
                    decisions[attribute_ref],
                    target_resolution_reason=(
                        "An absent or uncertain decision incorrectly carried document facts."
                    ),
                )
                continue
            decisions[attribute_ref] = replace(
                attribute,
                document_target="",
                document_spans=[],
                block_ids=[],
                entities=[],
                target_resolved=status == "absent",
                target_resolution_reason=reason,
            )
            valid_refs.add(attribute_ref)
            continue
        quotes: list[str] = []
        block_ids: list[str] = []
        spans: list[DocumentSpan] = []
        span_failure: _SpanValidation | None = None
        if not raw_spans:
            span_failure = _SpanValidation(
                span=None,
                code="missing_spans",
                reason="The present decision returned no supporting document spans.",
            )
        for raw_span in raw_spans:
            validation = _validated_claim_span(raw_span, source_blocks)
            if validation.span is None:
                span_failure = validation
                logger.warning(
                    "target_resolver rejected span for %s: code=%s reason=%s "
                    "block_id=%r",
                    attribute_ref,
                    validation.code,
                    validation.reason,
                    (
                        raw_span.get("block_id")
                        if isinstance(raw_span, dict)
                        else None
                    ),
                )
                break
            quote = validation.span.quote
            cited_ids = validation.span.block_ids
            if quote not in quotes:
                quotes.append(quote)
                spans.append(validation.span)
            block_ids.extend(cited_ids)
        if span_failure is not None or not quotes:
            decisions[attribute_ref] = replace(
                decisions[attribute_ref],
                target_resolution_reason=(
                    span_failure.reason
                    if span_failure is not None
                    else "The present decision contained no valid exact quotation."
                ),
            )
            continue
        target = " ".join(quotes)
        entities = [
            entity
            for entity in parse_evidence_entities(item.get("entities"))
            if entity.name.casefold() in target.casefold()
        ]
        decisions[attribute_ref] = replace(
            attribute,
            document_target=target,
            document_spans=spans,
            block_ids=list(dict.fromkeys(block_ids)),
            entities=entities,
            target_resolved=True,
            target_resolution_reason=reason,
        )
        valid_refs.add(attribute_ref)
    return _LedgerValidation(decisions=decisions, valid_refs=valid_refs)


def _validated_claim_span(
    raw_span: object,
    source_blocks: dict[str, str],
) -> _SpanValidation:
    """Resolve one selected source range into an exact canonical quotation."""
    if not isinstance(raw_span, dict):
        return _SpanValidation(
            span=None,
            code="invalid_span_shape",
            reason="A supporting span was not a structured source-line selection.",
        )
    block_id = str(raw_span.get("block_id", "")).strip()
    if block_id not in source_blocks:
        return _SpanValidation(
            span=None,
            code="unknown_block_id",
            reason=(
                "A supporting span cited an unknown document block ID: "
                + (block_id or "<empty>")
                + "."
            ),
        )
    selected = selected_source_lines(raw_span, source_blocks)
    if selected is None:
        return _SpanValidation(
            span=None,
            code="invalid_line_range",
            reason=(
                "A supporting span selected an invalid or empty source line range in "
                + block_id
                + "."
            ),
        )
    quote, block_id = selected
    return _SpanValidation(
        span=DocumentSpan(quote=quote, block_ids=[block_id]),
        code="valid",
        reason="The selected source lines were copied from the cited document block.",
    )

def _ledger_system_prompt(
    attributes: list[Attribute],
    requested: list[Attribute],
    *,
    retry: bool = False,
) -> str:
    catalog = "\n".join(
        f"- {attribute.name}: {attribute.description}" for attribute in attributes
    )
    requested_refs = "\n".join(f"- {attribute.name}" for attribute in requested)
    retry_instruction = (
        "A prior response omitted or malformed these decisions. "
        if retry
        else ""
    )
    return (
        "You create the one canonical document-claim ledger for a fixed evaluation "
        "vocabulary. Review the uploaded document against the COMPLETE field catalog "
        "as one shared ledger, so neighboring fields cannot independently claim the same "
        "statement.\n\n"
        f"Field catalog:\n{catalog}\n\n"
        f"Required output fields:\n{requested_refs}\n\n"
        f"{retry_instruction}Return exactly one binding for every required output "
        "field and no others. status=present only when the "
        "document directly states a target, constraint, assumption, or commitment for "
        "that field. status=absent means the supplied document does not state a qualifying "
        "target, including when it contains only adjacent discussion, TBD values, or an "
        "unspecified member of the field category. status=uncertain is reserved for supplied "
        "content that is unreadable, incomplete, or genuinely conflicting, not merely a "
        "missing target. Do not map a possible downstream "
        "implication or a neighboring table value. Assign each atomic claim to its single "
        "primary field in the complete catalog. Do not duplicate a formulation, dose, "
        "regimen, presentation, pharmacokinetic, safety, tolerability, or resistance claim "
        "under a broader product field merely because it describes the same product. A "
        "compound source statement may bind multiple fields only when it directly and "
        "independently states a different atomic meaning for each one. Preserve all explicitly "
        "included population segments; a highlighted subgroup does not replace a broader "
        "stated population. An unfilled "
        "heading, template prompt, or question is not a claim. In question-and-answer "
        "documents, select the answer block; include the question block only when its "
        "wording is necessary to preserve the answer's meaning.\n\n"
        "For present bindings, spans must select the smallest complete source line range "
        "needed to preserve labels, numbers, dates, comparators, populations, regimens, "
        f"and qualifiers. {LINE_SPAN_JSON_INSTRUCTION} For absent or uncertain "
        "bindings spans and entities must be empty. Extract entities only when explicitly "
        "named in the cited spans, and copy each name exactly as written there. If a "
        "target is visible only in an image and has no "
        "exact supplied source text, use uncertain rather than inventing a quotation. "
        "Return only the schema JSON."
    )


def _ledger_user_message(
    document_context: str,
    requested: list[Attribute],
) -> str:
    requested_refs = ", ".join(attribute.name for attribute in requested)
    return (
        f"Uploaded document blocks:\n{render_line_addressable_context(document_context)}\n\n"
        f"Return one decision for each required field: {requested_refs}."
    )
