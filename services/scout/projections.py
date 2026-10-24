"""Deterministic product-development projections over normalized Findings.

Grouping is by identity, and identity is decided once, upstream: which program and
product names denote one thing is `projection_reconciler`'s partition, passed in as
``names`` (each name as a provider stated it, to the name its group is shown under).
Nothing here folds case or spacing to decide that two names are one, and a record
repeated across fields or lanes is merged by its record identity
(`services.searcher.dedupe_findings`), not its page.
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Mapping

from services.searcher import Finding, dedupe_findings

from .models import (
    DevelopmentProgram,
    SafetyObservation,
)


def projection_names(findings_by_attribute: Mapping[str, list[Finding]]) -> list[str]:
    """Every program and product name the projections would group, as stated, in order."""
    return list(dict.fromkeys(
        name
        for findings in findings_by_attribute.values()
        for finding in findings
        for name in (
            *(record.program_name.strip() for record in finding.development_records),
            *(record.product_name.strip() for record in finding.safety_observations),
        )
        if name
    ))


def build_development_landscape(
    findings_by_attribute: Mapping[str, list[Finding]],
    names: Mapping[str, str] | None = None,
) -> list[DevelopmentProgram]:
    """Group explicit provider facts by named program without inference."""
    names = names or {}
    grouped: dict[str, DevelopmentProgram] = {}
    findings: dict[str, list[Finding]] = {}
    roles: dict[str, set[str]] = {}
    for attribute_ref, attribute_findings in findings_by_attribute.items():
        for finding in attribute_findings:
            for record in finding.development_records:
                stated = record.program_name.strip()
                if not stated:
                    continue
                key = names.get(stated, stated)
                program = grouped.setdefault(key, DevelopmentProgram(name=key))
                _append(program.sponsors, record.sponsor)
                _append(program.phases, record.phase)
                _append(program.statuses, record.status)
                _append(program.record_types, record.record_type)
                _append(program.record_ids, record.record_id)
                _append(program.attribute_refs, attribute_ref)
                findings.setdefault(key, []).append(finding)
                if record.source_role != "unknown":
                    roles.setdefault(key, set()).add(record.source_role)
    for key, program in grouped.items():
        program.projection_id = _projection_id("dp", key)
        program.source_role = _grouped_role(roles.get(key, set()))
        program.supporting_findings = _one_entry_per_record(findings[key])
    # Presentation order only - most advanced first, then by name. The phase is read
    # from the provider's own label (AGENTS: lexical rules may reorder results already
    # returned), because no adapter states a phase in a closed vocabulary yet.
    return sorted(
        grouped.values(),
        key=lambda item: (-_highest_phase(item.phases), item.name.casefold()),
    )


def build_safety_observations(
    findings_by_attribute: Mapping[str, list[Finding]],
    names: Mapping[str, str] | None = None,
) -> list[SafetyObservation]:
    """Group repeated retrievals of the same explicit safety observation.

    One observation is one product (by the reconciled name), one record type and
    source system (closed vocabularies), and one label as the source system states it.
    """
    names = names or {}
    grouped: dict[tuple[str, str, str, str], SafetyObservation] = {}
    findings: dict[tuple[str, str, str, str], list[Finding]] = {}
    roles: dict[tuple[str, str, str, str], set[str]] = {}
    for attribute_ref, attribute_findings in findings_by_attribute.items():
        for finding in attribute_findings:
            for record in finding.safety_observations:
                stated = record.product_name.strip()
                product = names.get(stated, stated)
                key = (product, record.record_type, record.source_system, record.label.strip())
                observation = grouped.setdefault(
                    key,
                    SafetyObservation(
                        product_name=product,
                        record_type=record.record_type,
                        source_system=record.source_system,
                        label=record.label.strip(),
                        detail=record.detail.strip(),
                        report_count=record.report_count,
                        qualification=record.qualification.strip(),
                    ),
                )
                if record.detail and len(record.detail) > len(observation.detail):
                    observation.detail = record.detail.strip()
                if record.report_count is not None:
                    observation.report_count = max(
                        observation.report_count or 0,
                        record.report_count,
                    )
                if not observation.qualification and record.qualification:
                    observation.qualification = record.qualification.strip()
                _append(observation.attribute_refs, attribute_ref)
                findings.setdefault(key, []).append(finding)
                if record.source_role != "unknown":
                    roles.setdefault(key, set()).add(record.source_role)
    for key, observation in grouped.items():
        observation.projection_id = _projection_id("so", "\n".join(key))
        observation.source_role = _grouped_role(roles.get(key, set()))
        observation.supporting_findings = _one_entry_per_record(findings[key])
    order = {
        "label_warning": 0,
        "recall": 1,
        "device_event": 2,
        "reported_event": 3,
    }
    return sorted(
        grouped.values(),
        key=lambda item: (
            item.product_name.casefold(),
            order.get(item.record_type, 9),
            item.source_system,
            -(item.report_count or 0),
            item.label.casefold(),
        ),
    )


def _append(values: list[str], value: str) -> None:
    normalized = value.strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _one_entry_per_record(findings: list[Finding]) -> list[Finding]:
    """One entry per record, its lineage merged the way Searcher's dedup merges it.

    The same record retrieved under two fields, or by two lanes, is one source: listing
    it twice would count it twice, and keeping only one would drop a lane. Copies,
    because the retrieved Finding is shared with each field's own evidence list.
    """
    return dedupe_findings(copy.copy(finding) for finding in findings)


def _projection_id(prefix: str, grouping_key: str) -> str:
    digest = hashlib.sha256(
        f"{prefix}\n{grouping_key}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _grouped_role(roles: set[str]) -> str:
    return next(iter(roles)) if len(roles) == 1 else "unknown"


def _highest_phase(phases: list[str]) -> int:
    values: list[int] = []
    roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
    for phase in phases:
        if match := re.search(r"\b([0-4])\b", phase):
            values.append(int(match.group(1)))
            continue
        if match := re.search(r"\b(IV|III|II|I)\b", phase.upper()):
            values.append(roman[match.group(1)])
    return max(values, default=-1)
