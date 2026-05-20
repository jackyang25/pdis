"""LLM-based extractor for `source_kind=product_profile` documents.

Walks all chunker `ContentBlock`s and asks an LLM to emit one draft Claim
per source-grounded assertion found in the text. Handles all block_types
(headings, paragraphs, table_rows) uniformly — not just structured tables.

The AttributeConfig is provided as **context** (preamble + attribute
namespace) so the LLM knows what kinds of claims are worth extracting,
but the extractor does NOT assign `attribute_ref`. That's the binder's
job in the next stage.

Hallucination guard: every claim must cite a `block_id` (must reference
a real block) and a `quote` (must be a verbatim substring of that block's
content). Claims failing validation are dropped silently.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import re
from typing import Any

from services.chunker import ContentBlock

from ..models import CLAIM_TYPES, POLARITIES, AttributeConfig, Claim, LLMClientProtocol


logger = logging.getLogger(__name__)


DEFAULT_MAX_OUTPUT_TOKENS = 16000
EXTRACTOR_VERSION = "product_profile@1"


def extract_product_profile(
    blocks: list[ContentBlock],
    source_id: str,
    *,
    config: AttributeConfig,
    llm_client: LLMClientProtocol,
    intervention_class: str | None = None,
    indication: str | None = None,
    extracted_at: str | None = None,
    source_url: str | None = None,
    model_id: str | None = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> list[Claim]:
    """Emit draft Claims from a parsed product-profile document via LLM.

    Args:
        blocks: chunker output for the source document.
        source_id: stable identifier for this document.
        config: AttributeConfig providing vocabulary + preamble context.
        llm_client: LLM to call for extraction.
        intervention_class: optional scoping tag stamped on each claim.
        indication: optional scoping tag stamped on each claim.
        extracted_at: ISO date for the extraction run (defaults to today).
        max_tokens: LLM response token budget.

    Returns:
        list of draft Claim objects (attribute_ref=None — binder handles binding).
    """
    if extracted_at is None:
        extracted_at = _dt.date.today().isoformat()
    if not blocks:
        return []

    block_by_id = {block.id: block for block in blocks}
    system_prompt, user_message = _build_prompts(blocks, config)
    prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]
    raw_response = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)

    try:
        parsed = _parse_response(raw_response)
    except ValueError:
        logger.warning("Extractor response was not valid JSON; retrying once")
        retry_message = (
            f"{user_message}\n\n"
            "Your previous response was not valid JSON. Return ONLY one JSON "
            'object with a "claims" array matching the schema above. No prose, '
            "no markdown fences."
        )
        raw_response = llm_client.call(system_prompt, retry_message, max_tokens=max_tokens)
        try:
            parsed = _parse_response(raw_response)
        except ValueError:
            logger.warning("Extractor response invalid after retry; returning no claims")
            return []

    claims: list[Claim] = []
    for entry in parsed:
        claim = _build_claim(
            entry,
            block_by_id=block_by_id,
            source_id=source_id,
            extracted_at=extracted_at,
            intervention_class=intervention_class,
            indication=indication,
            config=config,
            source_url=source_url,
            model_id=model_id,
            prompt_hash=prompt_hash,
        )
        if claim is not None:
            claims.append(claim)
    return claims


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompts(blocks: list[ContentBlock], config: AttributeConfig) -> tuple[str, str]:
    """Return (system_prompt, user_message)."""
    system_prompt = _build_system_prompt(config)
    user_message = _build_user_message(blocks)
    return system_prompt, user_message


def _build_system_prompt(config: AttributeConfig) -> str:
    claim_type_lines = ", ".join(sorted(set(config.claim_types) & set(CLAIM_TYPES)))
    polarity_lines = ", ".join(POLARITIES)
    attribute_hints = "\n".join(
        f"- {attr.name}: {attr.description.strip()[:200]}"
        for attr in config.attributes
    )

    return f"""You extract source-backed claims from product-profile documents (Target Product Profiles, Preferred Product Characteristics, peer-org equivalents).

DOMAIN CONTEXT
{config.preamble.strip()}

WHAT TO LOOK FOR
You're extracting claims worth grading and binding to attributes downstream. The attributes that exist (so you know what kinds of facts matter) are listed below — but DO NOT assign attribute_ref. Just extract the claims; another stage will bind them.

ATTRIBUTES (context only — do not output these as refs):
{attribute_hints}

WHAT COUNTS AS A CLAIM
A claim is one atomic, source-backed assertion. Examples:
- "Minimum efficacy is at least 50% reduction in clinical disease over 12 months"
- "Target population is children 6 months to 5 years in malaria-endemic areas"
- "Product must achieve WHO Prequalification by 2030"

INCLUSION TEST — apply this to every candidate claim:
> Could this claim change a number, threshold, or scope choice in a TPP draft?

If yes, extract it. If no, drop it. We are not building a general knowledge
store — we are building decision-grounding evidence for product development
teams. Mechanism-of-action background, general epidemiology unrelated to a
product's target population, and operational research on existing products
all fail this test.

A claim is also NOT:
- Section headings on their own
- Boilerplate / introductions / instructions
- Page numbers, references, version histories
- Empty cells or placeholder tokens like <<TBD>>

EXTRACTION RULES
1. Process EVERY block (paragraphs, headings, table_rows). A heading can be the start of a claim — e.g. "Indication: malaria" is one claim from one block.
2. A single block (especially a table_row) may contain multiple claims. Split them.
3. Each claim cites:
   - "block_id": the id of the block this claim came from. Must exactly match a block we provided.
   - "quote": a verbatim substring from that block's content. Must appear character-for-character in the source.
4. Use claim_type from: {claim_type_lines}
5. Use polarity from: {polarity_lines}
6. Do NOT output an "attribute_ref" — binding happens downstream.

OUTPUT SCHEMA
Return ONE JSON object exactly matching:
{{
  "claims": [
    {{
      "statement": "one normalized assertion, full sentence",
      "claim_type": "performance|feasibility|user_need|workflow|access|market|regulatory|modelled_impact|expert_judgment",
      "polarity": "supports|challenges|neutral",
      "block_id": "the block id this claim came from",
      "quote": "verbatim substring from that block's content"
    }}
  ]
}}

No markdown fences, no preamble, no trailing prose. Only the JSON object."""


def _build_user_message(blocks: list[ContentBlock]) -> str:
    lines = ["Extract claims from these blocks:"]
    for block in blocks:
        heading_path = " > ".join(block.heading_stack) if block.heading_stack else ""
        prefix = f"[{block.id} | {block.block_type}"
        if heading_path:
            prefix += f" | heading: {heading_path}"
        prefix += "]"
        lines.append(f"\n{prefix}\n{block.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing + validation
# ---------------------------------------------------------------------------


def _parse_response(raw: str) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of claim dicts. Raises ValueError on bad JSON."""
    text = raw.strip()
    # Strip markdown code fences if present.
    fence_match = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "claims" not in data:
        raise ValueError("response must be an object with a 'claims' array")
    claims = data["claims"]
    if not isinstance(claims, list):
        raise ValueError("'claims' must be a list")
    return claims


def _build_claim(
    entry: dict[str, Any],
    *,
    block_by_id: dict[str, ContentBlock],
    source_id: str,
    extracted_at: str,
    intervention_class: str | None,
    indication: str | None,
    config: AttributeConfig,
    source_url: str | None,
    model_id: str | None,
    prompt_hash: str,
) -> Claim | None:
    """Validate a single extracted claim dict; return a Claim or None if invalid."""
    statement = (entry.get("statement") or "").strip()
    block_id = entry.get("block_id")
    quote = entry.get("quote") or ""
    if not statement or not block_id or not quote:
        return None

    block = block_by_id.get(block_id)
    if block is None:
        logger.debug("Dropping claim: block_id %s not in source", block_id)
        return None
    if quote not in block.content:
        logger.debug("Dropping claim: quote not a verbatim substring of block %s", block_id)
        return None

    claim_type = entry.get("claim_type") or "performance"
    if claim_type not in config.claim_types:
        claim_type = "performance"
    polarity = entry.get("polarity") or "neutral"
    if polarity not in POLARITIES:
        polarity = "neutral"

    return Claim(
        id="",  # assigned downstream
        ordinal=-1,
        statement=statement,
        claim_type=claim_type,
        polarity=polarity,
        source_id=source_id,
        source_kind="product_profile",
        source_locator=_build_locator(block, quote),
        extracted_at=extracted_at,
        intervention_class=intervention_class,
        indication=indication,
        attribute_ref=None,
        source_url=source_url,
        extractor_version=EXTRACTOR_VERSION,
        model_id=model_id,
        prompt_hash=prompt_hash,
    )


def _build_locator(block: ContentBlock, quote: str) -> dict[str, Any]:
    locator: dict[str, Any] = {
        "block_id": block.id,
        "quote": quote,
        "block_type": block.block_type,
    }
    if block.heading_stack:
        locator["heading_stack"] = list(block.heading_stack)
    if block.structural_meta.get("page") is not None:
        locator["page"] = block.structural_meta["page"]
    if block.structural_meta.get("table_index") is not None:
        locator["table_index"] = block.structural_meta["table_index"]
    if block.structural_meta.get("row_index") is not None:
        locator["row_index"] = block.structural_meta["row_index"]
    return locator
