"""Stateless evidence pipeline.

Wires the five stages — parse (chunker) → extract → bind → appraise →
return — into a single function. No persistence in the active path; the
caller decides what to do with the output (display, download, write to
a file).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from chunker.stages.parser import parse_document
from chunker.models import ContentBlock

from .stages.appraiser import appraise_claims
from .stages.binder import bind_claims
from .stages.extractor_product_profile import extract_product_profile
from .llm_client import DEFAULT_MAX_OUTPUT_TOKENS, LLMClient
from .models import AttributeConfig, Claim


# Maps source_type -> the extractor function that recognizes it.
EXTRACTORS = {
    "product_profile": extract_product_profile,
}


def run_pipeline(
    *,
    file_path: str,
    doc_id: str,
    source_type: str,
    source_id: str,
    config: AttributeConfig,
    llm_client: LLMClient,
    intervention_class: str | None = None,
    therapeutic_area: str | None = None,
    extracted_at: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> tuple[list[ContentBlock], list[Claim]]:
    """
    Run the full evidence pipeline on one document.

    Returns:
        (blocks, claims) — the intermediate chunker output and the
        finalized claims. Caller decides what to persist.
    """
    if source_type not in EXTRACTORS:
        supported = ", ".join(sorted(EXTRACTORS))
        raise ValueError(
            f"No extractor registered for source_type='{source_type}'. "
            f"Supported: {supported}"
        )

    blocks = parse_document(file_path, doc_id)
    claims = _run_pipeline_on_blocks(
        blocks=blocks,
        source_type=source_type,
        source_id=source_id,
        config=config,
        llm_client=llm_client,
        intervention_class=intervention_class,
        therapeutic_area=therapeutic_area,
        extracted_at=extracted_at,
        max_tokens=max_tokens,
    )
    return blocks, claims


def run_pipeline_on_blocks(
    *,
    blocks: list[ContentBlock],
    source_type: str,
    source_id: str,
    config: AttributeConfig,
    llm_client: LLMClient,
    intervention_class: str | None = None,
    therapeutic_area: str | None = None,
    extracted_at: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> list[Claim]:
    """Same as run_pipeline but skips parsing — useful when blocks are already in hand."""
    return _run_pipeline_on_blocks(
        blocks=blocks,
        source_type=source_type,
        source_id=source_id,
        config=config,
        llm_client=llm_client,
        intervention_class=intervention_class,
        therapeutic_area=therapeutic_area,
        extracted_at=extracted_at,
        max_tokens=max_tokens,
    )


def _run_pipeline_on_blocks(
    *,
    blocks: list[ContentBlock],
    source_type: str,
    source_id: str,
    config: AttributeConfig,
    llm_client: LLMClient,
    intervention_class: str | None,
    therapeutic_area: str | None,
    extracted_at: str | None,
    max_tokens: int,
) -> list[Claim]:
    if extracted_at is None:
        extracted_at = _dt.date.today().isoformat()

    extractor = EXTRACTORS[source_type]
    drafts = extractor(
        blocks,
        source_id=source_id,
        intervention_class=intervention_class,
        therapeutic_area=therapeutic_area,
        extracted_at=extracted_at,
    )
    if not drafts:
        return drafts

    bound = bind_claims(drafts, config, llm_client, max_tokens=max_tokens)
    finalized = appraise_claims(bound)

    # Assign stable IDs + ordinals so the output is self-contained and
    # reproducible. (When a persistent backend lands later, it can use or
    # override these — the pipeline still produces them either way.)
    for ordinal, claim in enumerate(finalized):
        claim.ordinal = ordinal
        claim.id = f"{source_id}/c-{ordinal:04d}"

    return finalized


def default_source_id_from_path(file_path: str) -> str:
    """Derive a fallback source_id from a file path (stem, lowercased)."""
    return Path(file_path).stem.lower()
