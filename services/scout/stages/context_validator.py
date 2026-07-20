"""Validate configured retrieval context against the uploaded document.

The configured indication is authoritative for retrieval, but it must not be
allowed to silently conflict with a document that clearly concerns another
disease.  This stage performs one bounded, block-cited preflight assessment.
It blocks only explicit mismatches; absent or ambiguous context remains
``uncertain`` so documents that use unusual terminology are not rejected.
"""

from __future__ import annotations

import json
import logging
import re

from ..context import document_block_ids, limit_document_context, validated_block_ids
from ..models import DocumentContextValidation, LLMClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8000


def validate_document_context(
    document_context: str,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    images: list[dict[str, str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> DocumentContextValidation:
    """Return a conservative, cited indication/configuration assessment."""
    configured = indication.strip()
    if not document_context.strip():
        return DocumentContextValidation(
            status="uncertain",
            configured_indication=configured,
            reason="The uploaded document contained no readable content to validate.",
        )

    allowed_ids = document_block_ids(document_context)
    raw = llm_client.call(
        _system_prompt(configured),
        _user_message(document_context),
        max_tokens=max_tokens,
        images=images,
    )
    parsed = _parse(raw)
    if parsed is None:
        logger.warning("context_validator produced no parsable JSON; retrying once")
        raw = llm_client.call(
            _system_prompt(configured),
            _user_message(document_context),
            max_tokens=max_tokens,
            images=images,
        )
        parsed = _parse(raw)

    if parsed is None:
        return DocumentContextValidation(
            status="uncertain",
            configured_indication=configured,
            reason="The document indication could not be verified.",
        )

    status = str(parsed.get("status", "")).strip().lower()
    if status not in {"match", "mismatch", "uncertain"}:
        status = "uncertain"
    block_ids = validated_block_ids(parsed.get("block_ids"), allowed_ids)
    document_indication = str(parsed.get("document_indication", "")).strip()
    reason = str(parsed.get("reason", "")).strip()

    # A model may not block or affirm a run without exact document evidence.
    if status in {"match", "mismatch"} and not block_ids:
        status = "uncertain"
        reason = "The document indication could not be tied to an exact document block."
    if not reason:
        reason = "The document indication could not be verified."

    return DocumentContextValidation(
        status=status,
        configured_indication=configured,
        document_indication=document_indication,
        reason=reason,
        doc_block_ids=block_ids,
    )


def mismatch_message(validation: DocumentContextValidation) -> str:
    detected = validation.document_indication or "a different indication"
    return (
        f'Configured indication "{validation.configured_indication}" conflicts with '
        f'the uploaded document, which concerns "{detected}". '
        "Select the matching indication and run the analysis again."
    )


def _system_prompt(indication: str) -> str:
    return (
        "You validate ONE configuration value before evidence retrieval.\n\n"
        f'Configured indication: "{indication}".\n\n'
        "Determine whether the uploaded document is actually about that disease or "
        "condition. Account for acronyms, pathogens, subtypes, synonyms, and closely "
        "related clinical terminology. Do not judge the document's claims and do not "
        "infer a different configuration.\n\n"
        "Choose exactly one status:\n"
        "- match: the document clearly concerns the configured indication.\n"
        "- mismatch: the document clearly centers a different indication. Use this only "
        "for an explicit conflict, never merely because the indication is unstated.\n"
        "- uncertain: the indication is absent, peripheral, ambiguous, or there is not "
        "enough evidence to decide.\n\n"
        "Cite the exact [block:<id>] markers that establish the document indication. "
        "For match or mismatch, at least one block is required. Keep the reason factual "
        "and under 30 words. Return ONLY JSON:\n"
        '{"status":"match|mismatch|uncertain","document_indication":"...",'
        '"reason":"...","block_ids":["document/b-0001"]}'
    )


def _user_message(document_context: str) -> str:
    return (
        "Uploaded document blocks:\n"
        f"{limit_document_context(document_context)}\n\n"
        "Validate the configured indication now."
    )


def _parse(raw: str) -> dict | None:
    text = _strip_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_object(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_fences(value: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", value, re.DOTALL)
    return match.group(1) if match else value


def _extract_json_object(value: str) -> str:
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return value[index : index + end]
    raise ValueError("no JSON object")
