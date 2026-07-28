"""Deterministic integrity checks for the Inspector result contract."""

from __future__ import annotations

from services.chunker import ContentBlock

from .models import DIMENSIONS, InspectionConfig, InspectionResult


def validate_result_contract(
    result: InspectionResult,
    blocks: list[ContentBlock],
    config: InspectionConfig,
) -> None:
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
    if len({block.id for block in blocks}) != len(blocks):
        raise ValueError("Inspector source block IDs must be unique")
    if any(block.doc_id != result.doc_id for block in blocks):
        raise ValueError("Inspector result contains blocks from another document")
    block_by_id = {block.id: block for block in blocks}
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
        if any(name not in expected_variables for name in section.missing_variables):
            raise ValueError("Inspector missing_variables contains an unknown rubric variable")
        allowed_section_blocks = {
            block.id for block in blocks if block.section_label == section.section_name
        }
        for variable in section.variable_grades:
            if set(variable.dimensions) != expected_dimensions:
                raise ValueError(f"Inspector variable {variable.variable_name} has invalid dimensions")
            if len(variable.block_ids) != len(set(variable.block_ids)):
                raise ValueError("Inspector variable block lineage must be unique")
            if any(block_id not in allowed_section_blocks for block_id in variable.block_ids):
                raise ValueError("Inspector variable cited a block outside its mapped section")

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
