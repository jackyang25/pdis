"""Deterministic integrity checks for the Inspector result contract.

Determinism's whole job here: check what can be checked without reading prose. The
assessment covers exactly the rubric's units, every verdict cites blocks that exist
in the section it is about, and absence is the only claim allowed to cite nothing.

Two checks left with the nesting they policed: "no unit raises the same reason
twice" and "an absent unit cannot also raise other findings". A unit carries one
verdict now, so neither is expressible.

These hold for a result this process just built and for one imported from a file,
which is why they live here rather than only at parse time.
"""

from __future__ import annotations

from .assembly import rubric_units
from .models import (
    VERDICTS,
    Assessment,
    InspectionConfig,
    InspectionResult,
)


def validate_result_contract(
    result: InspectionResult,
    config: InspectionConfig,
) -> InspectionResult:
    """Return ``result`` after enforcing its closed rubric and block lineage.

    Blocks are read from the result rather than passed alongside it: the pipeline
    stamps them on immediately before validating, so a second parameter could only
    drift from the value being checked.
    """
    if result.assessment_status != "complete":
        raise ValueError(
            "Inspector assessment must be complete before a final result is emitted"
        )
    if result.consistency_status not in {
        "complete",
        "partial",
        "failed",
        "not_applicable",
        "unknown",
    }:
        raise ValueError("Inspector consistency status is invalid")
    if result.consistency_status not in {"complete", "partial"} and result.document_findings:
        raise ValueError("Inspector consistency findings require a completed check")
    if len({block.id for block in result.blocks}) != len(result.blocks):
        raise ValueError("Inspector source block IDs must be unique")
    if any(block.doc_id != result.doc_id for block in result.blocks):
        raise ValueError("Inspector result contains blocks from another document")

    block_by_id = {block.id: block for block in result.blocks}
    expected_sections = [section.name for section in config.sections]
    if [section.section_name for section in result.sections] != expected_sections:
        raise ValueError("Inspector sections do not match the rubric, in order")

    # --- The rubric owns the denominator -------------------------------------
    expected_units = rubric_units(config)
    actual_units = [
        (section.section_name, unit.variable_name, unit.optional)
        for section in result.sections
        for unit in section.units
    ]
    if actual_units != expected_units:
        raise ValueError("Inspector units do not match the rubric, in order")

    seen_ids: set[str] = set()
    for section in result.sections:
        # Parse lineage: a deterministic assignment, validated rather than rebuilt.
        mapped = section.mapped_block_ids
        if len(mapped) != len(set(mapped)):
            raise ValueError("Inspector section block mapping must be unique")
        if any(block_id not in block_by_id for block_id in mapped):
            raise ValueError("Inspector section mapped an unknown block")
        if any(
            block_by_id[block_id].section_label != section.section_name
            for block_id in mapped
        ):
            raise ValueError("Inspector section mapped a block labelled for another section")
        # `is_present` is derived from this mapping, so "absent yet mapping blocks"
        # and "present yet mapping none" are no longer expressible and need no check.
        # What still needs one is the other half: a section the document never wrote
        # must say so on every unit beneath it, or the rest look assessed.
        if not section.is_present and any(
            unit.verdict != "not_present" for unit in section.units
        ):
            raise ValueError(
                f"Inspector section {section.section_name} is absent, so every unit "
                "beneath it must report it missing"
            )

        allowed = set(mapped)
        for unit in section.units:
            if unit.section_name != section.section_name:
                raise ValueError("Inspector unit is filed under the wrong section")
            _validate_assessment(unit, allowed, seen_ids)

    # --- Conflicts: findings no single unit owns ------------------------------
    all_block_ids = set(block_by_id)
    for item in result.document_findings:
        if item.section_name or item.variable_name:
            raise ValueError("Inspector conflict must not name a single unit")
        if item.verdict != "section_conflict":
            raise ValueError("Inspector document finding must use the section_conflict verdict")
        _validate_assessment(item, all_block_ids, seen_ids)
        sections = {
            block_by_id[block_id].section_label for block_id in item.cited_block_ids
        }
        if len(sections) < 2:
            raise ValueError(
                "Inspector cross-section finding must cite at least two sections"
            )
    return result


def _validate_assessment(
    item: Assessment,
    allowed_block_ids: set[str],
    seen_ids: set[str],
) -> None:
    if item.verdict not in VERDICTS:
        raise ValueError(f"Inspector assessment has an invalid verdict: {item.verdict!r}")
    if item.id in seen_ids:
        raise ValueError(f"Inspector assessment id is not unique: {item.id!r}")
    seen_ids.add(item.id)

    cited = item.cited_block_ids
    if len(cited) != len(set(cited)):
        raise ValueError("Inspector assessment block lineage must be unique")
    if any(block_id not in allowed_block_ids for block_id in cited):
        raise ValueError("Inspector assessment cited a block outside its scope")
    # `Assessment.__post_init__` already refuses an absent unit that cites, a cited
    # one that does not, a shortfall with no sentence and a sound unit with one.
    # Re-checking any of that here would be a second statement of one rule, so this
    # layer checks only what the dataclass cannot see: which blocks it could reach.
