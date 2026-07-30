"""Deterministic integrity checks for the Aligner result contract."""

from __future__ import annotations

from collections import Counter

from .models import AlignmentConfig, AlignmentResult, AlignmentUnit


def validate_result_contract(
    result: AlignmentResult,
    config: AlignmentConfig,
) -> AlignmentResult:
    """Return ``result`` after enforcing its closed vocabularies and lineage."""
    block_by_id = {block.id: block for block in result.blocks}
    if len(block_by_id) != len(result.blocks):
        raise ValueError("Aligner source block IDs must be unique")
    if result.reference_document.doc_id == result.comparison_document.doc_id:
        raise ValueError("Aligner document IDs must be distinct")
    if result.unit_types != config.unit_types or result.relations != config.relations:
        raise ValueError("Aligner result vocabularies do not match its configured contract")

    unit_by_id = {unit.id: unit for unit in result.units}
    if len(unit_by_id) != len(result.units):
        raise ValueError("Aligner unit IDs must be unique")
    allowed_unit_types = {item.name for item in config.unit_types}
    documents = {
        "reference": result.reference_document.doc_id,
        "comparison": result.comparison_document.doc_id,
    }
    if any(block.doc_id not in set(documents.values()) for block in result.blocks):
        raise ValueError("Aligner result contains a block from an unknown document")
    for unit in result.units:
        if unit.unit_type not in allowed_unit_types or not unit.statement.strip():
            raise ValueError("Aligner unit violates the controlled extraction contract")
        if unit.document_id != documents[unit.document_role]:
            raise ValueError("Aligner unit document identity does not match its role")
        if not unit.block_ids or len(unit.block_ids) != len(set(unit.block_ids)):
            raise ValueError("Aligner units require unique source-block lineage")
        if any(
            block_id not in block_by_id
            or block_by_id[block_id].doc_id != unit.document_id
            for block_id in unit.block_ids
        ):
            raise ValueError("Aligner unit cited a block outside its source document")

    allowed_relations = {item.name for item in config.relations}
    link_ids: set[str] = set()
    reference_counts: Counter[str] = Counter()
    used_comparison_ids: set[str] = set()
    introduced_ids: set[str] = set()
    for link in result.links:
        if link.id in link_ids or link.relation not in allowed_relations:
            raise ValueError("Aligner link violates the closed relation contract")
        link_ids.add(link.id)
        reference_units = _resolve_units(link.reference_unit_ids, unit_by_id, "reference")
        comparison_units = _resolve_units(link.comparison_unit_ids, unit_by_id, "comparison")
        if link.relation == "introduced":
            if reference_units or len(comparison_units) != 1:
                raise ValueError("Introduced links require one comparison unit and no reference")
            introduced_ids.add(comparison_units[0].id)
        elif link.relation == "missing":
            if len(reference_units) != 1 or comparison_units:
                raise ValueError("Missing links require one reference unit and no comparison")
        elif len(reference_units) != 1 or not comparison_units:
            raise ValueError("Mapped links require one reference and at least one comparison unit")
        reference_counts.update(unit.id for unit in reference_units)
        used_comparison_ids.update(unit.id for unit in comparison_units if link.relation != "introduced")
        if link.reference_block_ids != _block_ids(reference_units):
            raise ValueError("Aligner reference link lineage does not match its units")
        if link.comparison_block_ids != _block_ids(comparison_units):
            raise ValueError("Aligner comparison link lineage does not match its units")

    reference_ids = {
        unit.id for unit in result.units if unit.document_role == "reference"
    }
    comparison_ids = {
        unit.id for unit in result.units if unit.document_role == "comparison"
    }
    if set(reference_counts) != reference_ids or any(count != 1 for count in reference_counts.values()):
        raise ValueError("Every Aligner reference unit must appear in exactly one link")
    if introduced_ids != comparison_ids - used_comparison_ids:
        raise ValueError("Aligner introduced links do not match unused comparison units")

    expected_stats = Counter(link.relation for link in result.links)
    if (
        result.stats.reference_units != len(reference_ids)
        or result.stats.comparison_units != len(comparison_ids)
        or any(
            getattr(result.stats, relation) != expected_stats[relation]
            for relation in allowed_relations
        )
    ):
        raise ValueError("Aligner statistics do not match the validated link ledger")


def _resolve_units(
    ids: list[str], unit_by_id: dict[str, AlignmentUnit], role: str
) -> list[AlignmentUnit]:
    if len(ids) != len(set(ids)) or any(unit_id not in unit_by_id for unit_id in ids):
        raise ValueError("Aligner link contains duplicate or unknown unit IDs")
    units = [unit_by_id[unit_id] for unit_id in ids]
    if any(unit.document_role != role for unit in units):
        raise ValueError("Aligner link cites a unit from the wrong document role")
    return units


def _block_ids(units: list[AlignmentUnit]) -> list[str]:
    return list(dict.fromkeys(block_id for unit in units for block_id in unit.block_ids))
    return result
