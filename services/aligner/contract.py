"""Deterministic integrity checks for the Aligner result contract.

Structural only, and it stays that way: this module asks whether the result is
internally consistent, never whether the analysis was any good. It cannot tell you a
verdict is right; it can tell you the verdict is one of the five, that it cites the
document it claims to have read, and that every requirement was answered exactly once.

The citation check is the one that matters most here, because it is the only place the
direction of a comparison is enforced on the way out: a requirement's blocks must be in
the document that set the bar and a verdict's blocks in the document being measured. A
result that mixed them would read perfectly and be unfalsifiable.
"""

from __future__ import annotations

from .models import (
    ALIGNMENT_VERDICTS,
    AlignmentConfig,
    AlignmentResult,
    VERDICTS_REQUIRING_CITATION,
    VERDICTS_REQUIRING_GAP,
    describe_document,
)


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

    _validate_findings(result)

    # Reading the role description is what proves a source type is configurable
    # rather than special-cased. `describe_document` falls back to `default`, so
    # this can only fail when the config itself is malformed.
    for document in result.documents:
        if not describe_document(config, document.source_type):
            raise ValueError(
                f"Aligner has no role description for source type {document.source_type!r}"
            )

    return result


def _validate_findings(result: AlignmentResult) -> None:
    """Every finding belongs to a comparison, cites the right side, and is unique."""
    edges_by_id = {edge.edge_id: edge for edge in result.edges}
    blocks_by_doc: dict[str, set[str]] = {}
    for block in result.blocks:
        blocks_by_doc.setdefault(block.doc_id, set()).add(block.id)

    seen: set[str] = set()
    for finding in result.findings:
        edge = edges_by_id.get(finding.edge_id)
        if edge is None:
            raise ValueError(
                f"Aligner finding {finding.requirement_id} names comparison "
                f"{finding.edge_id!r}, which this result does not make"
            )
        if finding.requirement_id in seen:
            raise ValueError(
                f"Aligner judged {finding.requirement_id} more than once; a "
                "requirement has exactly one verdict per comparison"
            )
        seen.add(finding.requirement_id)

        if finding.verdict not in ALIGNMENT_VERDICTS:
            raise ValueError(
                f"Aligner finding {finding.requirement_id} carries unknown verdict "
                f"{finding.verdict!r}"
            )
        if not finding.requirement.strip():
            raise ValueError(
                f"Aligner finding {finding.requirement_id} states no requirement"
            )
        if not finding.statement.strip():
            raise ValueError(
                f"Aligner finding {finding.requirement_id} carries no statement of "
                "what the compared document says"
            )

        if bool(finding.gap.strip()) != (finding.verdict in VERDICTS_REQUIRING_GAP):
            raise ValueError(
                f"Aligner finding {finding.requirement_id} is {finding.verdict} and "
                "must "
                + (
                    "name the distance from the requirement in `gap`"
                    if finding.verdict in VERDICTS_REQUIRING_GAP
                    else "carry no `gap`"
                )
            )

        # The bar is stated in the reference document, so that is where its citation
        # must point. A requirement citing the document being measured would mean the
        # comparison quietly checked a document against itself.
        _require_blocks_in(
            finding.reference_block_ids,
            document=edge.reference_doc_id,
            blocks_by_doc=blocks_by_doc,
            what=f"requirement {finding.requirement_id}",
            side="reference",
        )
        if not finding.reference_block_ids:
            raise ValueError(
                f"Aligner requirement {finding.requirement_id} cites no passage in the "
                "document that sets the bar, so the bar cannot be checked"
            )

        if finding.verdict in VERDICTS_REQUIRING_CITATION:
            if not finding.comparison_block_ids:
                raise ValueError(
                    f"Aligner finding {finding.requirement_id} is {finding.verdict} "
                    "and must cite the passages it was read from"
                )
        elif finding.comparison_block_ids:
            raise ValueError(
                f"Aligner finding {finding.requirement_id} is {finding.verdict} and "
                "cannot cite a passage: it is a claim about the absence of one"
            )
        _require_blocks_in(
            finding.comparison_block_ids,
            document=edge.comparison_doc_id,
            blocks_by_doc=blocks_by_doc,
            what=f"finding {finding.requirement_id}",
            side="comparison",
        )


def _require_blocks_in(
    block_ids: list[str],
    *,
    document: str,
    blocks_by_doc: dict[str, set[str]],
    what: str,
    side: str,
) -> None:
    known = blocks_by_doc.get(document, set())
    unknown = [block_id for block_id in block_ids if block_id not in known]
    if unknown:
        raise ValueError(
            f"Aligner {what} cites {unknown} on the {side} side, which is not in "
            f"{document!r}"
        )
