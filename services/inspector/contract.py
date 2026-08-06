"""Deterministic integrity checks for the Inspector result contract.

Determinism's whole job here: check what can be checked without reading prose. The
assessment covers exactly the rubric's units, every finding cites blocks that exist
in the section it is about, absence is the only claim allowed to cite nothing, and
no unit raises the same reason twice.

These hold for a result this process just built and for one imported from a file,
which is why they live here rather than only at parse time.
"""

from __future__ import annotations

from .assembly import rubric_units
from .models import (
    FINDING_REASONS,
    UNCITED_REASON,
    Finding,
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
            UNCITED_REASON not in {f.reason for f in unit.findings}
            for unit in section.units
        ):
            raise ValueError(
                f"Inspector section {section.section_name} is absent, so every unit "
                "beneath it must report it missing"
            )

        allowed = set(mapped)
        for unit in section.units:
            reasons = [finding.reason for finding in unit.findings]
            if len(reasons) != len(set(reasons)):
                raise ValueError(
                    f"Inspector unit {unit.variable_name or section.section_name} "
                    "raises a reason twice"
                )
            if UNCITED_REASON in reasons and len(reasons) > 1:
                # Absence gates the rest. Code used to add a second finding of its
                # own here, so one absence was counted twice before the model spoke.
                raise ValueError(
                    f"Inspector unit {unit.variable_name or section.section_name} "
                    "is absent and cannot also raise other findings"
                )
            for finding in unit.findings:
                if (
                    finding.section_name != section.section_name
                    or finding.variable_name != unit.variable_name
                ):
                    raise ValueError("Inspector finding is filed against the wrong unit")
                _validate_finding(finding, allowed, seen_ids)

    # --- Conflicts: findings no single unit owns ------------------------------
    all_block_ids = set(block_by_id)
    for finding in result.document_findings:
        if finding.section_name or finding.variable_name:
            raise ValueError("Inspector conflict must not name a single unit")
        if finding.reason != "conflicting":
            raise ValueError("Inspector document finding must use the conflicting reason")
        _validate_finding(finding, all_block_ids, seen_ids)
        sections = {
            block_by_id[block_id].section_label for block_id in finding.cited_block_ids
        }
        if len(sections) < 2:
            raise ValueError(
                "Inspector cross-section finding must cite at least two sections"
            )
    return result


def _validate_finding(
    finding: Finding,
    allowed_block_ids: set[str],
    seen_ids: set[str],
) -> None:
    if finding.reason not in FINDING_REASONS:
        raise ValueError(f"Inspector finding has an invalid reason: {finding.reason!r}")
    if not finding.statement:
        raise ValueError("Inspector finding must state what is wrong")
    if finding.id in seen_ids:
        raise ValueError(f"Inspector finding id is not unique: {finding.id!r}")
    seen_ids.add(finding.id)

    cited = finding.cited_block_ids
    if len(cited) != len(set(cited)):
        raise ValueError("Inspector finding block lineage must be unique")
    if any(block_id not in allowed_block_ids for block_id in cited):
        raise ValueError("Inspector finding cited a block outside its scope")
    # `Finding.__post_init__` already refuses an absent finding that cites, and a
    # cited one that does not. Re-checking here would be a second statement of one
    # rule, so this layer checks only what the dataclass cannot see: which blocks
    # the finding was allowed to reach.
