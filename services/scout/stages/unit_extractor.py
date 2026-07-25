"""The 'extract' unit provider: pull a document's checkable units from the doc.

For doc types without a fixed attribute vocabulary (e.g. an IPDP), an LLM reads
the document and emits the same canonical ``Attribute`` shape as the fixed
provider: a neutral definition plus a separate document target and exact block
lineage. Only the definition provider differs downstream.

Self-gating / robust: an unreadable doc or unparsable reply yields no units,
which the pipeline treats like "no attributes" (empty result).
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from ..ai import request_structured
from ..ai_contracts import unit_batch
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
    LLMClientProtocol,
    parse_evidence_entities,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8000
UNIT_CONTEXT_CHARS = 350_000
UNIT_EXTRACTION_WORKERS = 4


def extract_units(
    doc_text: str,
    *,
    intervention_class: str,
    source_type: str,
    indication: str,
    llm_client: LLMClientProtocol,
    images_by_block_id: dict[str, str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Attribute]:
    """Extract the document's checkable units. Returns `Attribute`s (name unique
    within the run, used as the downstream `attribute_ref`)."""
    if not doc_text.strip():
        return []
    system_prompt = _system_prompt(intervention_class, source_type, indication)
    chunks = _document_chunks(doc_text)

    def extract_chunk(indexed: tuple[int, str]) -> list[Attribute]:
        chunk_index, chunk = indexed
        user_message = _user_message(chunk)
        allowed_block_ids = document_block_ids(chunk)
        contract = unit_batch(sorted(allowed_block_ids))
        images = [
            {"block_id": block_id, "data_url": image}
            for block_id, image in (images_by_block_id or {}).items()
            if block_id in allowed_block_ids
        ]
        parsed = request_structured(
            llm_client,
            contract,
            system_prompt,
            user_message,
            max_tokens=max_tokens,
            images=images or None,
        )
        chunk_units = _validated_units(parsed, chunk)
        if not chunk_units:
            logger.warning(
                "unit_extractor produced no parsable units for chunk %d; retrying once",
                chunk_index,
            )
            parsed = request_structured(
                llm_client,
                contract,
                system_prompt,
                user_message,
                max_tokens=max_tokens,
                images=images or None,
            )
            chunk_units = _validated_units(parsed, chunk)
        return chunk_units

    workers = max(1, min(UNIT_EXTRACTION_WORKERS, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(extract_chunk, enumerate(chunks)))
    units = [unit for chunk_units in results for unit in chunk_units]
    return _dedupe(units)


def _system_prompt(intervention_class: str, source_type: str, indication: str) -> str:
    return (
        "You extract the CHECKABLE UNITS from a product-development document so a "
        "downstream tool can test each against real-world evidence.\n\n"
        f"Document type: {source_type}. Product class: {intervention_class}. Indication: {indication}.\n\n"
        "A unit is a concrete assertion the document makes that could be confirmed or "
        "challenged by external evidence - a milestone with a date, a timeline, a cost or "
        "volume projection, a regulatory expectation, a feasibility or efficacy assumption, "
        "a manufacturing or access plan. Skip pure background, narrative, and boilerplate "
        "that makes no testable claim. An unfilled heading, template prompt, or question "
        "is not a unit. In question-and-answer documents, extract the answer's concrete "
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
    document_context: str,
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
        source_blocks = rendered_block_texts(document_context)
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


def _dedupe(units: list[Attribute]) -> list[Attribute]:
    """Ensure names are unique (they become the downstream attribute_ref)."""
    exact: dict[tuple[str, str, str], Attribute] = {}
    collapsed: list[Attribute] = []
    for unit in units:
        key = (
            unit.name,
            " ".join(unit.document_target.lower().split()),
            unit.evidence_domain,
        )
        existing = exact.get(key)
        if existing is not None:
            existing.block_ids = list(
                dict.fromkeys([*existing.block_ids, *unit.block_ids])
            )
            existing.document_spans = list(
                {
                    (span.quote, tuple(span.block_ids)): span
                    for span in [*existing.document_spans, *unit.document_spans]
                }.values()
            )
            existing.entities = list(
                dict.fromkeys([*existing.entities, *unit.entities])
            )
            continue
        exact[key] = unit
        collapsed.append(unit)

    seen: set[str] = set()
    out: list[Attribute] = []
    for unit in collapsed:
        name = unit.name
        i = 2
        while name in seen:
            name = f"{unit.name}_{i}"
            i += 1
        seen.add(name)
        out.append(
            Attribute(
                name=name,
                description=unit.description,
                block_ids=unit.block_ids,
                document_target=unit.document_target,
                document_spans=unit.document_spans,
                definition_mode="dynamic",
                target_resolved=True,
                target_resolution_reason=unit.target_resolution_reason,
                evidence_domain=unit.evidence_domain,
                entities=unit.entities,
            )
        )
    return out


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unit"
