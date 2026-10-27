"""Validate configured retrieval context against the uploaded document.

The configured indication is authoritative for retrieval, but it must not be
allowed to silently conflict with a document that clearly concerns another
disease.  This stage performs one bounded, block-cited preflight assessment.
It blocks only explicit mismatches; absent or ambiguous context remains
``uncertain`` so documents that use unusual terminology are not rejected. A check
whose answer stayed invalid after one retry, was refused, or whose provider failed is
``not_assessed`` with the failure's code: the run proceeds, but no one should read it
as the model's ``uncertain``.
"""

from __future__ import annotations

from shared.ai import RECORDABLE_FAILURES, Effort, ModelTask, failure_code
from shared.request_budget import check_request

from ..ai import request_validated
from ..ai_contracts import context_validation
from ..context import (
    BLOCK_ID_JSON_INSTRUCTION,
    document_block_ids,
    limit_document_context,
    validated_block_ids,
)
from ..models import (
    NOT_ASSESSED,
    VALID_CONTEXT_STATUSES,
    DocumentContextValidation,
    LLMClientProtocol,
)

#: The fast tier at low effort: a preflight that recognises which disease a document
#: is about and stops only on an explicit, cited conflict. The judgement is one of
#: recognition, not of weighing evidence, and the run's other stages do not wait on
#: anything subtler from it.
TASK: ModelTask = "fast"
EFFORT: Effort = "low"
#: One status, a short reason and a few block IDs; the rest is reasoning room.
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

    bounded_context = limit_document_context(document_context)
    allowed_ids = document_block_ids(bounded_context)
    contract = context_validation(sorted(allowed_ids))
    bounded_images = [
        image
        for image in (images or [])
        if image.get("block_id") in allowed_ids
    ] or None
    user_message = _user_message(bounded_context)
    check_request("Scout's document-context check", text=user_message, images=bounded_images)

    def parse(parsed: object) -> DocumentContextValidation:
        if not isinstance(parsed, dict):
            raise ValueError("no structured decision was returned")
        status = str(parsed.get("status", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip()
        if status not in VALID_CONTEXT_STATUSES or not reason:
            raise ValueError("a status from the closed list and a reason are required")
        block_ids = validated_block_ids(parsed.get("block_ids"), allowed_ids)
        # A model may not block or affirm a run without exact document evidence.
        if status in {"match", "mismatch"} and not block_ids:
            raise ValueError(f"{status} requires at least one cited document block")
        return DocumentContextValidation(
            status=status,
            configured_indication=configured,
            document_indication=str(parsed.get("document_indication", "")).strip(),
            reason=reason,
            doc_block_ids=block_ids,
        )

    try:
        return request_validated(
            llm_client,
            contract,
            build_system_prompt(configured),
            user_message,
            max_tokens=max_tokens,
            parse=parse,
            failure="The document indication could not be verified",
            images=bounded_images,
            task=TASK,
            effort=EFFORT,
        )
    except RECORDABLE_FAILURES as exc:
        return DocumentContextValidation(
            status=NOT_ASSESSED,
            configured_indication=configured,
            reason=str(exc),
            failure_code=failure_code(exc),
        )


def mismatch_message(validation: DocumentContextValidation) -> str:
    detected = validation.document_indication or "a different indication"
    return (
        f'Configured indication "{validation.configured_indication}" conflicts with '
        f'the uploaded document, which concerns "{detected}". '
        "Select the matching indication and run the analysis again."
    )


def build_system_prompt(indication: str) -> str:
    return (
        "You validate ONE configuration value before evidence retrieval.\n\n"
        f'Configured indication: "{indication}".\n\n'
        "Determine whether the uploaded document is actually about that disease or "
        "health need. Account for acronyms, pathogens, subtypes, synonyms, and closely "
        "related clinical terminology. Do not judge the document's claims and do not "
        "infer a different configuration.\n\n"
        "Choose exactly one status:\n"
        "- match: the document clearly concerns the configured indication.\n"
        "- mismatch: the document clearly centers a different indication. Use this only "
        "for an explicit conflict, never merely because the indication is unstated.\n"
        "- uncertain: the indication is absent, peripheral, ambiguous, or there is not "
        "enough evidence to decide.\n\n"
        "Cite the document blocks that establish the document indication. "
        "For match or mismatch, at least one block is required. Keep the reason factual "
        f"and under 30 words. {BLOCK_ID_JSON_INSTRUCTION}\n\n"
        "Return only the schema-bound response."
    )


def _user_message(document_context: str) -> str:
    return (
        "Uploaded document blocks:\n"
        f"{document_context}\n\n"
        "Validate the configured indication now."
    )
