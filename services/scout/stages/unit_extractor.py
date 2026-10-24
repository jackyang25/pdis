"""The 'extract' unit provider: pull a document's checkable units from the doc.

For doc types without a fixed attribute vocabulary (e.g. an IPDP), an LLM reads
the document and emits the same canonical ``Attribute`` shape as the fixed
provider: a neutral definition plus a separate document target and exact block
lineage. Only the definition provider differs downstream.

A valid empty response means no checkable units. Incomplete or invalid replies
fail the run rather than masquerading as that conclusion.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from shared.ai import Effort, ModelTask
from shared.batching import map_ordered
from shared.request_budget import check_request

from ..ai import request_validated
from ..ai_contracts import unit_batch
from .unit_reconciler import reconcile_units
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
    EVIDENCE_DOMAINS,
    ENTITY_TYPES,
    IdentityReconciliation,
    LLMClientProtocol,
    parse_evidence_entities,
)


#: One document chunk per request: which claims a document states is a fact about the
#: whole text, so the chunk is the set the answer describes.
CHUNKS_PER_REQUEST = 1
#: The reasoning tier at medium effort: every downstream stage investigates what this
#: stage decides is a claim, and a missed claim is never searched.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "medium"
# Whole-document extraction needs room for both reasoning and the cited units.
DEFAULT_MAX_TOKENS = 32000
UNIT_CONTEXT_CHARS = 350_000
UNIT_EXTRACTION_WORKERS = 4


def extract_units(
    doc_text: str,
    *,
    intervention_class: str,
    source_type: str,
    indication: str,
    llm_client: LLMClientProtocol,
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    progress_callback: Callable[..., None] | None = None,
) -> tuple[list[Attribute], IdentityReconciliation | None]:
    """Extract the document's checkable units, and what their identity layer decided.

    Returns `Attribute`s whose names are unique within the run (the downstream
    `attribute_ref`), and the reconciliation record when there were units to compare.
    """
    if not doc_text.strip():
        return [], None
    system_prompt = build_system_prompt(intervention_class, source_type, indication)
    chunks = _document_chunks(doc_text)
    if progress_callback:
        progress_callback("units")

    def extract_chunk(indexed: tuple[int, str]) -> list[Attribute]:
        chunk_index, chunk = indexed
        allowed_block_ids = document_block_ids(chunk)
        source_blocks = rendered_block_texts(chunk)

        def parse(parsed: object) -> list[Attribute]:
            chunk_units = _validated_units(parsed, source_blocks)
            if not isinstance(parsed, list) or len(chunk_units) != len(parsed):
                raise ValueError(
                    f"the model did not return valid cited claims for chunk {chunk_index}"
                )
            return chunk_units

        return request_validated(
            llm_client,
            unit_batch(sorted(allowed_block_ids)),
            system_prompt,
            _user_message(chunk),
            max_tokens=max_tokens,
            images=[image for image in images or [] if image["block_id"] in allowed_block_ids]
            or None,
            parse=parse,
            failure="Document claim extraction failed",
            task=TASK,
            effort=EFFORT,
        )

    for chunk in chunks:
        chunk_ids = document_block_ids(chunk)
        check_request(
            "Scout's claim extraction",
            text=_user_message(chunk),
            images=[image for image in images or [] if image["block_id"] in chunk_ids],
        )
    results = map_ordered(
        list(enumerate(chunks)), extract_chunk, workers=UNIT_EXTRACTION_WORKERS
    )
    units = [unit for chunk_units in results for unit in chunk_units]
    if len(units) > 1 and progress_callback:
        progress_callback("unit_reconciliation")
    reconciled, record = reconcile_units(units, llm_client, images=images)
    return _unique_names(reconciled), record


def build_system_prompt(intervention_class: str, source_type: str, indication: str) -> str:
    return (
        "You extract the CHECKABLE UNITS from a product-development document so a "
        "downstream tool can test each against real-world evidence.\n\n"
        f"Document type: {source_type}. Product class: {intervention_class}. Indication: {indication}.\n\n"
        "A unit is a commitment, target, assumption, or reported result the document "
        "states that external evidence - published studies, registries, regulatory "
        "guidance, prior programmes - could confirm or challenge: a performance, efficacy, "
        "or safety target; a milestone date or development timeline that comparable "
        "programmes' realised timelines could judge; a cost, price, or volume projection; "
        "a regulatory or policy expectation; a study design; a feasibility, manufacturing, "
        "or access assumption.\n\n"
        "Skip progress reports on the programme's own work - that a task is complete, "
        "under way, or not started, or that a supplier or design has been chosen - because "
        "only the programme's own records could confirm them. A result or dated commitment "
        "stated beside such a report is still a unit. Skip pure background, narrative, and "
        "boilerplate that makes no testable claim. An unfilled heading, template prompt, or "
        "question is not a unit. In question-and-answer documents, extract the answer's concrete "
        "claim and select its answer block; include the question only when needed to "
        "preserve meaning.\n\n"
        "For each unit return:\n"
        "- name: a short snake_case label, unique within the document (e.g. "
        '"regulatory_approval_timeline", "cogs_per_dose_target").\n'
        "- description: one neutral sentence defining what will be evaluated; do not "
        "put the document's specific number, date, or commitment here.\n"
        f"- evidence_domain: exactly one of {', '.join(sorted(EVIDENCE_DOMAINS))}.\n"
        "- spans: the smallest complete source line selections that together state "
        "the concrete claim/target while preserving every number, date, comparator, "
        f"and qualifier. {LINE_SPAN_JSON_INSTRUCTION}\n\n"
        "- entities: only names explicitly stated in those spans whose type is one "
        f"of {', '.join(sorted(ENTITY_TYPES - {'other'}))}. Include an "
        "identifier only if the document states it. Copy each entity name exactly "
        "as written in the selected source lines.\n\n"
        "Return the units in the schema-bound `units` array."
    )


def _user_message(doc_text: str) -> str:
    return (
        f"Document:\n{render_line_addressable_context(doc_text)}\n\n"
        "Extract the checkable units now."
    )


def _document_chunks(doc_text: str) -> list[str]:
    """Split only between annotated blocks; no document text is discarded."""
    return chunk_document_context(doc_text, max_chars=UNIT_CONTEXT_CHARS)


def _validated_units(
    parsed: object,
    source_blocks: dict[str, str],
) -> list[Attribute]:
    if not isinstance(parsed, list):
        return []
    out: list[Attribute] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        evidence_domain = str(item.get("evidence_domain", "")).strip().lower()
        if not description or evidence_domain not in EVIDENCE_DOMAINS:
            continue
        spans: list[DocumentSpan] = []
        raw_spans = item.get("spans")
        raw_spans = raw_spans if isinstance(raw_spans, list) else []
        for raw_span in raw_spans:
            selected = selected_source_lines(raw_span, source_blocks)
            if selected is None:
                spans = []
                break
            quote, block_id = selected
            spans.append(DocumentSpan(quote=quote, block_ids=[block_id]))
        if not spans:
            continue
        document_target = " ".join(dict.fromkeys(span.quote for span in spans))
        block_ids = list(
            dict.fromkeys(
                block_id for span in spans for block_id in span.block_ids
            )
        )
        out.append(
            Attribute(
                name=_slug(str(item.get("name", ""))),
                description=description,
                block_ids=block_ids,
                document_target=document_target,
                document_spans=spans,
                definition_mode="dynamic",
                target_resolved=True,
                target_resolution_reason=(
                    "The dynamic claim was extracted from exact document spans."
                ),
                evidence_domain=evidence_domain,
                entities=[
                    entity
                    for entity in parse_evidence_entities(item.get("entities"))
                    if entity.name.casefold() in document_target.casefold()
                ],
            )
        )
    return out


def _unique_names(units: list[Attribute]) -> list[Attribute]:
    """Allocate downstream references, never decide semantic identity."""
    seen: set[str] = set()
    out: list[Attribute] = []
    for unit in units:
        name = unit.name
        i = 2
        while name in seen:
            name = f"{unit.name}_{i}"
            i += 1
        seen.add(name)
        out.append(replace(unit, name=name))
    return out


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unit"
