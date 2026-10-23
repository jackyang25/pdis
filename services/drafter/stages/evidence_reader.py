"""What one source says about one variable, in its own words.

One source per request: each source's reading is independent, and reading several in one
prompt lets one paper's number colour another's. The model owns what the text means - which
product, what was measured, the value and its unit as written. Code checks only that the
quote is in the excerpt and decides, from the lane, whether that text may supply a number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from services.searcher import Finding, source_specs
from shared.ai import request_structured
from shared.quotes import quote_in_text
from shared.vocabulary import AttributeDefinition

from ..models import BASES, LLMClientProtocol, ObservedValue

FINDINGS_PER_REQUEST = 1
#: Sources read per variable, in the order retrieval ranked them.
MAX_FINDINGS_PER_VARIABLE = 8
MAX_EXCERPT_CHARS = 8000
MAX_TOKENS = 12000  # reasoning counts against it; a reply cut off is a failure
#: The lanes whose text may supply a number - Scout's rule, for the same reason: their
#: excerpts are the source's own words and the source reports evidence rather than opinion.
NUMERIC_EVIDENCE_CLASSES = frozenset({"literature", "registry", "regulatory"})

_NUMBER = {"type": ["number", "null"]}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["observations"],
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["basis", "product", "measure", "quote", "value", "lower", "upper", "unit"],
                "properties": {
                    "basis": {"type": "string", "enum": list(BASES)},
                    "product": {"type": "string"},
                    "measure": {"type": "string"},
                    "quote": {"type": "string", "minLength": 1},
                    "value": _NUMBER,
                    "lower": _NUMBER,
                    "upper": _NUMBER,
                    "unit": {"type": "string"},
                },
            },
        },
    },
}


@dataclass(frozen=True)
class ReadObservation:
    """An observation before the pipeline numbers it."""
    basis: str
    url: str
    title: str
    source_label: str
    product: str
    measure: str
    quote: str
    value: ObservedValue | None
    numeric_eligible: bool


def build_system_prompt() -> str:
    return (
        "You read ONE source excerpt for ONE variable of an intervention target product profile "
        "(iTPP) that a team is drafting, and report what the excerpt says about that variable.\n\n"
        "Report two kinds of observation, and never mix them:\n"
        "- comparable_product: what an existing or investigational product achieved, showed or is "
        "specified to have for this variable. Name the product.\n"
        "- published_guidance: what a target product profile, guideline, prequalification or "
        "programme requirement asks of a product for this variable. Name the publisher as product.\n\n"
        "For each, copy the exact words from the excerpt that state it as quote. Give a number only "
        "as the excerpt writes it: value for a single figure, lower and upper for a range, the unit "
        "exactly as written; leave numbers null for a statement in words. Report nothing when the "
        "excerpt does not speak to this variable for this disease."
    )


def eligible_findings(findings: Sequence[Finding]) -> list[Finding]:
    """Evidence with text to read, bounded per variable and shared across sources.

    Taken in turn from each source, keeping each source's own order. Findings arrive grouped
    by source in the config's order, so a cut taken from the top went entirely to the first
    source listed - a general web lane - and the literature, registry and guidance behind it,
    the only text that may supply a figure, was never read.
    """
    by_lane: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.evidence_role == "evidence" and (finding.excerpt or "").strip():
            by_lane.setdefault(finding.excerpt_source_lane or finding.source, []).append(finding)
    queues = list(by_lane.values())
    chosen: list[Finding] = []
    while len(chosen) < MAX_FINDINGS_PER_VARIABLE and any(queues):
        for queue in queues:
            if queue and len(chosen) < MAX_FINDINGS_PER_VARIABLE:
                chosen.append(queue.pop(0))
    return chosen


def read_finding(
    variable: AttributeDefinition,
    finding: Finding,
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_term: str,
) -> list[ReadObservation] | None:
    """The source's observations, or None when no usable reading came back twice."""
    excerpt = (finding.excerpt or "")[:MAX_EXCERPT_CHARS]
    message = (
        f"Product type: {intervention_term}. Disease / condition: {indication}.\n"
        f"Variable: {variable.name}\nWhat it covers: {variable.description.strip()}\n\n"
        f"Source: {finding.title}\nExcerpt:\n{excerpt}"
    )
    for attempt in range(2):
        repair = "\n\nYour prior answer was not a usable reading. Answer again." if attempt else ""
        payload = request_structured(
            llm_client, build_system_prompt(), message + repair,
            schema_name="drafter_evidence_reading", schema=SCHEMA, max_tokens=MAX_TOKENS,
        )
        if isinstance(payload, dict) and isinstance(payload.get("observations"), list):
            return _observations(payload["observations"], finding, excerpt)
    return None


def _observations(items: list, finding: Finding, excerpt: str) -> list[ReadObservation]:
    lane = finding.excerpt_source_lane or finding.source
    spec = {spec.key: spec for spec in source_specs()}.get(lane)
    lane_supplies_numbers = bool(spec and spec.excerpt_is_verbatim and spec.evidence_class in NUMERIC_EVIDENCE_CLASSES)
    label = finding.source_labels.get(lane) or (spec.label if spec else lane)
    observations: list[ReadObservation] = []
    for item in items:
        if not isinstance(item, dict) or item.get("basis") not in BASES:
            continue
        quote = " ".join(str(item.get("quote") or "").split())
        if not quote_in_text(quote, excerpt):
            continue
        value = _value(item)
        observations.append(ReadObservation(
            basis=item["basis"],
            url=finding.url,
            title=finding.title,
            source_label=label,
            product=" ".join(str(item.get("product") or "").split()),
            measure=" ".join(str(item.get("measure") or "").split()),
            quote=quote,
            value=value,
            numeric_eligible=item["basis"] == "comparable_product" and value is not None and lane_supplies_numbers,
        ))
    return observations


def _value(item: dict) -> ObservedValue | None:
    numbers = {key: item.get(key) for key in ("value", "lower", "upper")}
    if all(number is None for number in numbers.values()):
        return None
    if any(number is not None and not isinstance(number, (int, float)) for number in numbers.values()):
        return None
    return ObservedValue(
        value=float(numbers["value"]) if numbers["value"] is not None else None,
        lower=float(numbers["lower"]) if numbers["lower"] is not None else None,
        upper=float(numbers["upper"]) if numbers["upper"] is not None else None,
        unit=" ".join(str(item.get("unit") or "").split()),
    )
