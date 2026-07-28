"""Typed, service-owned wire primitives for Scout model calls.

These models define what the model may return.  They intentionally validate
shape and internal consistency only; provenance and consumer-specific
eligibility are checked by the stage that owns those boundaries.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SemanticSlotWire(_WireModel):
    state: Literal["specified", "not_specified", "unknown", "other"]
    value: str
    other: str

    @model_validator(mode="after")
    def validate_payload(self) -> "SemanticSlotWire":
        if self.state == "specified" and (not self.value or self.other):
            raise ValueError("specified requires value and no other text")
        if self.state == "other" and (not self.other or self.value):
            raise ValueError("other requires other text and no specified value")
        if self.state not in {"specified", "other"} and (self.value or self.other):
            raise ValueError("absent and unknown slots cannot carry values")
        return self


class TernaryDecisionWire(_WireModel):
    state: Literal["yes", "no", "unknown"]
    reason: str

    @model_validator(mode="after")
    def validate_reason(self) -> "TernaryDecisionWire":
        if self.state != "yes" and not self.reason:
            raise ValueError("no and unknown decisions require a reason")
        return self


class EvidenceUnitIdentityWire(_WireModel):
    """Source-stated arm/cohort identity only when a record has distinct units."""

    status: Literal["resolved", "record_level", "uncertain"]
    group: SemanticSlotWire
    cohort: SemanticSlotWire
    reason: str

    @model_validator(mode="after")
    def validate_identity(self) -> "EvidenceUnitIdentityWire":
        asserted = any(
            slot.state in {"specified", "other"}
            for slot in (self.group, self.cohort)
        )
        if self.status == "resolved" and not asserted:
            raise ValueError("resolved evidence units require a group or cohort")
        if self.status != "resolved" and asserted:
            raise ValueError("unresolved evidence units cannot assert group or cohort identity")
        if not self.reason:
            raise ValueError("evidence unit identity requires a reason")
        return self


class EvidenceUnitPartitionWire(_WireModel):
    """Whether one source record contains independent comparison units."""

    status: Literal["single_unit", "disjoint_units", "overlapping_or_uncertain"]
    reason: str

    @model_validator(mode="after")
    def validate_partition(self) -> "EvidenceUnitPartitionWire":
        if not self.reason:
            raise ValueError("evidence unit partition requires a reason")
        return self


class NumericExpressionWire(_WireModel):
    kind: Literal[
        "point_estimate",
        "range",
        "bound",
        "confidence_interval",
        "count",
        "rate",
        "other",
        "unknown",
    ]
    unit: str
    value: float | None
    lower: float | None
    upper: float | None
    comparator: Literal["", "=", ">", ">=", "<", "<="]

    @model_validator(mode="after")
    def validate_expression(self) -> "NumericExpressionWire":
        for value in (self.value, self.lower, self.upper):
            if value is not None and not math.isfinite(value):
                raise ValueError("numeric values must be finite")
        if self.kind not in {"other", "unknown"} and not self.unit:
            raise ValueError("numeric expressions require a unit")
        if self.kind in {"point_estimate", "count", "rate"}:
            if self.value is None:
                raise ValueError("atomic scalars require exactly one value")
            # Structured-output schemas cannot express every cross-field rule.
            # Canonicalize redundant null-equivalent fields rather than losing
            # a valid measurement because the model repeated '=' or a bound.
            self.lower = None
            self.upper = None
            self.comparator = ""
        elif self.kind == "bound":
            if (
                self.value is None
                or not self.comparator
            ):
                raise ValueError("bounds require one value and a comparator")
            self.lower = None
            self.upper = None
        elif self.kind in {"range", "confidence_interval"}:
            if (
                self.lower is None
                or self.upper is None
                or self.lower > self.upper
            ):
                raise ValueError("intervals require ordered lower and upper values")
            self.value = None
            self.comparator = ""
        return self


class TargetExpressionWire(_WireModel):
    kind: Literal["bound"]
    unit: str
    value: float
    lower: None
    upper: None
    comparator: Literal["=", ">", ">=", "<", "<="]

    @model_validator(mode="after")
    def validate_expression(self) -> "TargetExpressionWire":
        if not self.unit or not math.isfinite(self.value):
            raise ValueError("target bounds require a finite value and unit")
        return self


def inline_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a self-contained schema fragment suitable for composition.

    Pydantic may place shared definitions under ``$defs``. Scout embeds wire
    primitives inside request-specific schemas, so local references are
    resolved once here instead of maintaining a second handwritten shape.
    """

    schema = deepcopy(model.model_json_schema())
    definitions = schema.pop("$defs", {})

    def resolve(value: Any) -> Any:
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if not isinstance(value, dict):
            return value
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.rsplit("/", 1)[-1]
            return resolve(deepcopy(definitions[name]))
        return {
            key: resolve(item)
            for key, item in value.items()
            if key not in {"title", "default"}
        }

    return resolve(schema)
