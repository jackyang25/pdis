"""Deterministic integrity checks for the Inspector result contract."""

from __future__ import annotations

from .models import (
    ABSENT_CONTENT_STATUS,
    CONTENT_STATUSES,
    DIMENSIONS,
    InspectionConfig,
    InspectionResult,
    PRESENT_CONTENT_STATUSES,
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
    expected_dimensions = set(DIMENSIONS)
    if set(result.dimensions) != expected_dimensions:
        raise ValueError("Inspector document dimensions do not match the closed contract")
    if result.grading_status != "complete":
        raise ValueError("Inspector core grading must be complete before a final result is emitted")
    if result.consistency_status not in {
        "complete",
        "partial",
        "failed",
        "not_applicable",
        "unknown",
    }:
        raise ValueError("Inspector consistency status is invalid")
    if result.consistency_status not in {"complete", "partial"} and result.cross_section_findings:
        raise ValueError("Inspector consistency findings require a completed check")
    if len({block.id for block in result.blocks}) != len(result.blocks):
        raise ValueError("Inspector source block IDs must be unique")
    if any(block.doc_id != result.doc_id for block in result.blocks):
        raise ValueError("Inspector result contains blocks from another document")
    block_by_id = {block.id: block for block in result.blocks}
    expected_sections = [section.name for section in config.sections]
    if [section.section_name for section in result.section_grades] != expected_sections:
        raise ValueError("Inspector section ledger does not match rubric order")

    spec_by_name = {section.name: section for section in config.sections}
    for section in result.section_grades:
        if set(section.dimensions) != expected_dimensions:
            raise ValueError(f"Inspector section {section.section_name} has invalid dimensions")
        spec = spec_by_name[section.section_name]
        expected_variables = [variable.name for variable in spec.variables]
        if section.is_present and expected_variables:
            actual_variables = [variable.variable_name for variable in section.variable_grades]
            if actual_variables != expected_variables:
                raise ValueError(
                    f"Inspector variable ledger for {section.section_name} does not match its rubric"
                )
        elif not section.is_present and section.variable_grades:
            raise ValueError("A missing Inspector section cannot contain variable grades")
        # The section mapping is published by the grader, so it is validated here
        # rather than rebuilt from `section_label` a second time.
        if len(section.mapped_block_ids) != len(set(section.mapped_block_ids)):
            raise ValueError("Inspector section block mapping must be unique")
        if any(block_id not in block_by_id for block_id in section.mapped_block_ids):
            raise ValueError("Inspector section mapped an unknown block")
        if any(
            block_by_id[block_id].section_label != section.section_name
            for block_id in section.mapped_block_ids
        ):
            raise ValueError("Inspector section mapped a block labelled for another section")
        if not section.is_present and section.mapped_block_ids:
            raise ValueError("An absent Inspector section cannot map source blocks")
        allowed_section_blocks = set(section.mapped_block_ids)

        for variable in section.variable_grades:
            if set(variable.dimensions) != expected_dimensions:
                raise ValueError(f"Inspector variable {variable.variable_name} has invalid dimensions")
            if variable.content_status not in CONTENT_STATUSES:
                raise ValueError(
                    f"Inspector variable {variable.variable_name} has an invalid content status"
                )
            absent = variable.content_status == ABSENT_CONTENT_STATUS
            for dimension, grade in variable.dimensions.items():
                cited = grade.cited_block_ids
                if len(cited) != len(set(cited)):
                    raise ValueError("Inspector dimension block lineage must be unique")
                if any(block_id not in allowed_section_blocks for block_id in cited):
                    raise ValueError(
                        "Inspector dimension cited a block outside its mapped section"
                    )
                # Absence is the one claim that cannot carry lineage. Keeping this
                # check here, rather than only at parse time, means it also holds
                # for an imported result.
                if absent and cited:
                    raise ValueError(
                        f"Absent Inspector variable {variable.variable_name} cannot cite a block"
                    )
            if (
                variable.content_status in PRESENT_CONTENT_STATUSES
                and not variable.dimensions["completeness"].cited_block_ids
            ):
                raise ValueError(
                    f"Present Inspector variable {variable.variable_name} must cite a source block"
                )

    valid_section_names = set(expected_sections)
    for finding in result.cross_section_findings:
        if len(finding.sections) < 2 or any(
            section not in valid_section_names for section in finding.sections
        ):
            raise ValueError("Inspector cross-section finding has invalid section lineage")
        if not finding.block_ids or any(
            block_id not in block_by_id for block_id in finding.block_ids
        ):
            raise ValueError("Inspector cross-section finding has invalid block lineage")
        for section_name in finding.sections:
            if not any(
                block_by_id[block_id].section_label == section_name
                for block_id in finding.block_ids
            ):
                raise ValueError(
                    "Inspector cross-section finding must cite every named section"
                )
    return result
