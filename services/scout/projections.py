"""Deterministic product-development projections over normalized Findings."""

from __future__ import annotations

import hashlib
import re

from services.searcher import Finding

from .models import (
    BurdenIndicator,
    DevelopmentProgram,
    IndicatorReading,
    SafetyObservation,
)


def build_development_landscape(
    findings_by_attribute: dict[str, list[Finding]],
) -> list[DevelopmentProgram]:
    """Group explicit provider facts by named program without inference."""
    grouped: dict[str, DevelopmentProgram] = {}
    roles: dict[str, set[str]] = {}
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
                if record.source_role != "unknown":
                    roles.setdefault(key, set()).add(record.source_role)
    for key, program in grouped.items():
        program.projection_id = _projection_id("dp", key)
        program.source_role = _grouped_role(roles.get(key, set()))
    return sorted(
        grouped.values(),
        key=lambda item: (-_highest_phase(item.phases), item.name.casefold()),
    )


def build_burden_indicators(
    findings_by_attribute: dict[str, list[Finding]],
) -> list[BurdenIndicator]:
    """Group indicator readings by indicator, keeping every place and year stated.

    Deduplicated on the full reading - indicator, place, year - because the same
    country-year row can arrive from more than one request and it is one reading, not two.
    Nothing is aggregated: a total across whichever countries happened to be retrieved
    would read as a total for the disease.
    """
    grouped: dict[str, BurdenIndicator] = {}
    seen: dict[str, set[tuple[str, int]]] = {}
    for attribute_ref, findings in findings_by_attribute.items():
        for finding in findings:
            for record in finding.indicator_records:
                indicator = grouped.setdefault(
                    record.indicator_code,
                    BurdenIndicator(
                        indicator_code=record.indicator_code,
                        indicator_name=record.indicator_name,
                    ),
                )
                if record.indicator_name and not indicator.indicator_name:
                    indicator.indicator_name = record.indicator_name
                readings = seen.setdefault(record.indicator_code, set())
                key = (record.place, record.year)
                if key not in readings:
                    readings.add(key)
                    indicator.readings.append(
                        IndicatorReading(
                            place=record.place,
                            spatial_type=record.spatial_type,
                            year=record.year,
                            value=record.value,
                            value_text=record.value_text,
                            parent_place=record.parent_place,
                        )
                    )
                _append(indicator.attribute_refs, attribute_ref)
                _append_finding(indicator.supporting_findings, finding)
    for code, indicator in grouped.items():
        indicator.projection_id = _projection_id("bi", code)
        # Newest first, then by place, so a reader sees the current picture before the
        # history of any one country.
        indicator.readings.sort(key=lambda r: (-r.year, r.place))
    return sorted(
        grouped.values(),
        key=lambda item: (-(item.latest_year or 0), item.indicator_name.casefold()),
    )


def build_safety_observations(
    findings_by_attribute: dict[str, list[Finding]],
) -> list[SafetyObservation]:
    """Group repeated retrievals of the same explicit safety observation."""
    grouped: dict[tuple[str, str, str, str], SafetyObservation] = {}
    roles: dict[tuple[str, str, str, str], set[str]] = {}
    for attribute_ref, findings in findings_by_attribute.items():
        for finding in findings:
            for record in finding.safety_observations:
                key = (
                    _key(record.product_name),
                    record.record_type.casefold(),
                    record.source_system.casefold(),
                    _key(record.label),
                )
                observation = grouped.setdefault(
                    key,
                    SafetyObservation(
                        product_name=record.product_name.strip(),
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
                _append_finding(observation.supporting_findings, finding)
                if record.source_role != "unknown":
                    roles.setdefault(key, set()).add(record.source_role)
    for key, observation in grouped.items():
        observation.projection_id = _projection_id("so", "\n".join(key))
        observation.source_role = _grouped_role(roles.get(key, set()))
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
            item.source_system.casefold(),
            -(item.report_count or 0),
            item.label.casefold(),
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
