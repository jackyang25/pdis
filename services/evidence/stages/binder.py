"""Binder: assigns `attribute_ref` and `binding_confidence` to draft claims.

Structurally parallel to chunker/mapper.py:
  - Takes a list of draft claims + an AttributeConfig.
  - Builds a constrained-vocabulary prompt.
  - Calls one LLM client.
  - Parses + validates JSON.
  - Merges the labels back onto the original Claim objects.

The binder is shared across all extractors. It is the only module that
actively consumes the AttributeConfig (extractor and appraiser don't
read the config's attribute vocabulary).
"""

from __future__ import annotations

import json
from typing import Any

from ..models import AttributeConfig, Claim, LLMClientProtocol


class BinderResponseError(Exception):
    """Raised when the binder response cannot be parsed or fails validation."""


def bind_claims(
    claims: list[Claim],
    config: AttributeConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> list[Claim]:
    """
    Fill `attribute_ref` and `binding_confidence` on each claim.

    Mutates and returns the same list of Claim objects (in place), so the
    caller can chain extract -> bind -> appraise without copying.

    Raises BinderResponseError on unrecoverable LLM output. Per-claim
    failures (missing ID, invalid attribute_ref) are recorded by leaving
    that claim's attribute_ref None and setting binding_confidence to "low".
    """
    if not claims:
        return claims

    system_prompt = _build_system_prompt(config)
    user_message = _build_user_message(claims)

    raw_response = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    decoded = _parse_response(raw_response)

    decisions_by_id: dict[str, dict] = {}
    for entry in decoded:
        claim_temp_id = entry.get("temp_id")
        if isinstance(claim_temp_id, str):
            decisions_by_id[claim_temp_id] = entry

    valid_attribute_names = {attr.name for attr in config.attributes}

    for index, claim in enumerate(claims):
        temp_id = _temp_id_for(index)
        decision = decisions_by_id.get(temp_id)
        if not decision:
            # No decision returned: leave unbound, mark low confidence.
            claim.attribute_ref = None
            claim.binding_confidence = "low"
            continue

        attribute_ref = decision.get("attribute_ref")
        confidence = decision.get("binding_confidence", "low")

        if (
            isinstance(attribute_ref, str)
            and attribute_ref in valid_attribute_names
        ):
            claim.attribute_ref = attribute_ref
            claim.binding_confidence = confidence if confidence in {"high", "medium", "low"} else "low"
        else:
            claim.attribute_ref = None
            claim.binding_confidence = "low"

    return claims


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_system_prompt(config: AttributeConfig) -> str:
    attribute_lines = "\n".join(
        f"  - {attr.name}: {attr.description}"
        for attr in config.attributes
    )
    return (
        "You are an attribute binder for an evidence layer over Target Product "
        "Profile (TPP) and Preferred Product Characteristics (PPC) documents.\n\n"
        f"{config.preamble}\n\n"
        "Each input claim is an atomic, source-backed assertion. Your job is to "
        "bind each claim to exactly one attribute from the list below.\n\n"
        "ATTRIBUTES (pick from these exact names):\n"
        f"{attribute_lines}\n\n"
        "Rules:\n"
        "  - Choose the single best attribute. If none fits well, return the "
        "closest with binding_confidence=\"low\".\n"
        "  - attribute_ref MUST be one of the names above, byte-for-byte.\n"
        "  - binding_confidence ∈ {\"high\", \"medium\", \"low\"}.\n"
        "  - Return a JSON array. One object per input claim. No prose.\n"
        "  - Each object: {\"temp_id\": \"...\", \"attribute_ref\": \"...\", "
        "\"binding_confidence\": \"...\"}\n"
    )


def _build_user_message(claims: list[Claim]) -> str:
    lines = []
    for index, claim in enumerate(claims):
        temp_id = _temp_id_for(index)
        intervention = claim.intervention_class or ""
        area = claim.therapeutic_area or ""
        scope = f" | intervention: {intervention} | area: {area}" if (intervention or area) else ""
        lines.append(
            f"[{temp_id} | claim_type: {claim.claim_type}{scope}]\n"
            f"<statement>{claim.statement}</statement>"
        )
    return "\n\n".join(lines)


def _temp_id_for(index: int) -> str:
    return f"c-{index:04d}"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_response(raw: str) -> list[dict[str, Any]]:
    text = _strip_markdown_fence(raw).strip()
    if not text:
        raise BinderResponseError("Binder returned empty response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BinderResponseError(f"Binder response is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise BinderResponseError("Binder response must be a JSON array")
    return data


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # Drop opening fence (possibly with language tag) and closing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text
