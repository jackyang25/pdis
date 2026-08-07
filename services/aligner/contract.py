"""Deterministic integrity checks for the Aligner result contract.

Structural only, and it stays that way: this module asks whether the result is
internally consistent, never whether the analysis was any good. Checks for a
closed finding vocabulary belong here too once one exists, added beside these
rather than folded into them.
"""

from __future__ import annotations

from .models import AlignmentConfig, AlignmentResult, describe_document


def validate_result_contract(
    result: AlignmentResult,
    config: AlignmentConfig,
) -> AlignmentResult:
    """Return ``result`` after enforcing document identity and block lineage."""
    if not result.documents:
        raise ValueError("Aligner result must carry at least one document")

    doc_ids = [document.doc_id for document in result.documents]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("Aligner document IDs must be distinct")

    source_types = [document.source_type for document in result.documents]
    if len(set(source_types)) != len(source_types):
        raise ValueError("Aligner cannot carry two documents of the same type")

    block_ids = {block.id for block in result.blocks}
    if len(block_ids) != len(result.blocks):
        raise ValueError("Aligner source block IDs must be unique")

    known = set(doc_ids)
    if any(block.doc_id not in known for block in result.blocks):
        raise ValueError("Aligner result contains a block from an unknown document")

    if not result.edges:
        raise ValueError("Aligner result must carry at least one comparison")
    for edge in result.edges:
        if edge.reference_doc_id not in known or edge.comparison_doc_id not in known:
            raise ValueError("Aligner comparison names a document not in this result")
        if edge.reference_doc_id == edge.comparison_doc_id:
            raise ValueError("Aligner comparison names one document on both sides")
        if not edge.question.strip():
            raise ValueError("Aligner comparison must state what it asks")

    # Reading the role description is what proves a source type is configurable
    # rather than special-cased. `describe_document` falls back to `default`, so
    # this can only fail when the config itself is malformed.
    for document in result.documents:
        if not describe_document(config, document.source_type):
            raise ValueError(
                f"Aligner has no role description for source type {document.source_type!r}"
            )

    return result
