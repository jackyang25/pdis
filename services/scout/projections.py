"""Deterministic product-development projections over normalized Findings."""

from __future__ import annotations

import re

from services.searcher import Finding

from .models import DevelopmentProgram, SafetySignal


def build_development_landscape(
    findings_by_attribute: dict[str, list[Finding]],
) -> list[DevelopmentProgram]:
    """Group explicit provider facts by named program without inference."""
    grouped: dict[str, DevelopmentProgram] = {}
    for attribute_ref, findings in findings_by_attribute.items():
        for finding in findings:
            for record in finding.development_records:
                key = _key(record.program_name)
                if not key:
                    continue
                program = grouped.setdefault(
                    key,
                    DevelopmentProgram(name=record.program_name.strip()),
                )
                _append(program.sponsors, record.sponsor)
                _append(program.phases, record.phase)
                _append(program.statuses, record.status)
                _append(program.record_types, record.record_type)
                _append(program.record_ids, record.record_id)
                _append(program.attribute_refs, attribute_ref)
                _append_finding(program.supporting_findings, finding)
    return sorted(
        grouped.values(),
        key=lambda item: (-_highest_phase(item.phases), item.name.casefold()),
    )


def build_safety_signals(
    findings_by_attribute: dict[str, list[Finding]],
) -> list[SafetySignal]:
    """Group repeated retrievals of the same explicit safety observation."""
    grouped: dict[tuple[str, str, str], SafetySignal] = {}
    for attribute_ref, findings in findings_by_attribute.items():
        for finding in findings:
            for record in finding.safety_records:
                key = (
                    _key(record.product_name),
                    record.signal_type.casefold(),
                    _key(record.signal),
                )
                signal = grouped.setdefault(
                    key,
                    SafetySignal(
                        product_name=record.product_name.strip(),
                        signal_type=record.signal_type,
                        signal=record.signal.strip(),
                        detail=record.detail.strip(),
                        count=record.count,
                        qualification=record.qualification.strip(),
                    ),
                )
                if record.detail and len(record.detail) > len(signal.detail):
                    signal.detail = record.detail.strip()
                if record.count is not None:
                    signal.count = max(signal.count or 0, record.count)
                if not signal.qualification and record.qualification:
                    signal.qualification = record.qualification.strip()
                _append(signal.attribute_refs, attribute_ref)
                _append_finding(signal.supporting_findings, finding)
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
            order.get(item.signal_type, 9),
            -(item.count or 0),
            item.signal.casefold(),
        ),
    )


def _append(values: list[str], value: str) -> None:
    normalized = value.strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _append_finding(findings: list[Finding], finding: Finding) -> None:
    if not any(
        existing.url == finding.url and existing.source == finding.source
        for existing in findings
    ):
        findings.append(finding)


def _key(value: str) -> str:
    return " ".join(value.casefold().split())


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
