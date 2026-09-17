"""Typed, service-owned wire primitives for Scout model calls.

These models define what the model may return.  They intentionally validate
shape and internal consistency only; provenance and consumer-specific
eligibility are checked by the stage that owns those boundaries.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    reason: str = Field(min_length=1)

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
    """Whether one source record contains independent comparison units.

    ``min_length`` is declared rather than checked after the fact so the
    published schema states the same requirement the parser enforces.
    """

    status: Literal["single_unit", "disjoint_units", "overlapping_or_uncertain"]
    reason: str = Field(min_length=1)


class NumericDisplayWire(_WireModel):
    kind: Literal["quantity", "calendar_year"] = "quantity"
    unit_singular: str = ""
    unit_plural: str = ""


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
    display: NumericDisplayWire = Field(default_factory=NumericDisplayWire)

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
    unit: str = Field(min_length=1)
    value: float
    lower: None
    upper: None
    comparator: Literal["=", ">", ">=", "<", "<="]
    display: NumericDisplayWire = Field(default_factory=NumericDisplayWire)

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
            nested = globals().get(name)
            if isinstance(nested, type) and issubclass(nested, _WireModel):
                return inline_json_schema(nested)
            return resolve(deepcopy(definitions[name]))
        resolved = {
            key: resolve(item)
            for key, item in value.items()
            if key not in {"title", "default"}
        }
        if resolved.get("type") == "object" and "properties" in resolved:
            # Provider outputs state every field; defaults serve code-created
            # fixtures, never make the model's response shape optional.
            resolved["required"] = list(resolved["properties"])
        return resolved

    result = resolve(schema)
    # Encode conditional field requirements in provider-supported anyOf
    # branches as well as the runtime validators. Ordered interval endpoints
    # and finite arithmetic remain deterministic cross-value checks.
    def variant(base: dict, changes: dict) -> dict:
        branch = deepcopy(base)
        branch["properties"].update(changes)
        return branch

    if model is SemanticSlotWire:
        return {"anyOf": [
            variant(result, {"state": {"type": "string", "enum": [state]},
                "value": {"type": "string", **({"minLength": 1} if state == "specified" else {"enum": [""]})},
                "other": {"type": "string", **({"minLength": 1} if state == "other" else {"enum": [""]})}})
            for state in ("specified", "other", "not_specified", "unknown")
        ]}
    if model is TernaryDecisionWire:
        return {"anyOf": [
            variant(result, {"state": {"type": "string", "enum": [state]},
                "reason": {"type": "string", **({"minLength": 1} if state != "yes" else {})}})
            for state in ("yes", "no", "unknown")
        ]}
    if model is EvidenceUnitIdentityWire:
        slots = inline_json_schema(SemanticSlotWire)["anyOf"]
        asserted = {"anyOf": slots[:2]}
        absent = {"anyOf": slots[2:]}
        return {"anyOf": [
            variant(result, {"status": {"type": "string", "enum": ["resolved"]}, "group": asserted}),
            variant(result, {"status": {"type": "string", "enum": ["resolved"]}, "group": absent, "cohort": asserted}),
            variant(result, {"status": {"type": "string", "enum": ["record_level", "uncertain"]}, "group": absent, "cohort": absent}),
        ]}
    if model is NumericExpressionWire:
        branches = []
        for kinds in (("point_estimate", "count", "rate"), ("bound",), ("range", "confidence_interval"), ("other", "unknown")):
            changes = {"kind": {"type": "string", "enum": list(kinds)}}
            if kinds[0] not in {"other", "unknown"}:
                changes["unit"] = {"type": "string", "minLength": 1}
                if kinds[0] == "range":
                    changes.update({"lower": {"type": "number"}, "upper": {"type": "number"}})
                else:
                    changes["value"] = {"type": "number"}
                if kinds[0] == "bound":
                    changes["comparator"] = {"type": "string", "enum": ["=", ">", ">=", "<", "<="]}
            branches.append(variant(result, changes))
        return {"anyOf": branches}
    return result
