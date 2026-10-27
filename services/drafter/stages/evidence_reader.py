"""What one source says about one variable, in its own words.

One source per request: each source's reading is independent, and reading several in one
prompt lets one paper's number colour another's. The model owns what the text means - which
product, what was measured, the value and its unit as written. Code checks only that the
quote is in the excerpt, that the words the reader says state the number are in the quote,
and decides, from the lane, whether that text may supply a number.

The number is the model's reading of those words, and code never re-reads them: parsing
"≥ 80 %" back into 80 would be the prose normalisation this suite refuses. What code can
check is that the words exist, so a value is always pinned to text a reader can see.

A quote the excerpt does not contain is never kept, and never silently lost either: the
reading is asked for once more with the quotes named, and whatever still fails is counted
on the reading so the result can say how much was set aside. A number whose words are not
in its quote is treated the same way: the observation is kept as words, and counted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from services.searcher import Finding, source_specs
from shared.ai import Effort, ModelTask, request_validated
from shared.errors import ModelResponseError
from shared.quotes import in_one_fragment, quote_in_text
from shared.schemas import blank_text, non_empty_text
from shared.vocabulary import AttributeDefinition, searchable_attribute_phrase

from ..models import BASES, LLMClientProtocol, ObservedValue

FINDINGS_PER_REQUEST = 1
#: Sources read per variable, in the order retrieval ranked them.
MAX_FINDINGS_PER_VARIABLE = 8
MAX_EXCERPT_CHARS = 8000
#: The fast tier, as Scout's insight extraction is: this copies quotes and values out of
#: one excerpt, code checks every quote, and the suggestion that weighs them stays on the
#: reasoning tier. One call per source per variable.
TASK: ModelTask = "fast"
#: Low: copying words out of at most 8000 characters needs little reasoning.
EFFORT: Effort = "low"
#: A few observations of a quote each; doubled once if a dense excerpt runs past it.
MAX_TOKENS = 6000
#: The lanes whose text may supply a number - Scout's rule, for the same reason: their
#: excerpts are the source's own words and the source reports evidence rather than opinion.
NUMERIC_EVIDENCE_CLASSES = frozenset({"literature", "registry", "regulatory"})

_NULL = {"type": "null"}
_NUMBER = {"type": "number"}


def _observation_schema(numbers: dict, *, unit: dict, value_text: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["basis", "product", "measure", "quote", "value", "lower", "upper", "unit", "value_text"],
        "properties": {
            "basis": {"type": "string", "enum": list(BASES)},
            "product": {"type": "string"},
            "measure": {"type": "string"},
            "quote": non_empty_text(),
            **numbers,
            "unit": unit,
            "value_text": value_text,
        },
    }


#: An observation is one of three shapes, and the schema says which fields each uses
#: rather than leaving "blank unless" to code: words with no number; one figure; or a
#: range, with an optional central figure. A number always carries the words stating it.
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["observations"],
    "properties": {
        "observations": {
            "type": "array",
            "items": {"anyOf": [
                _observation_schema({"value": _NULL, "lower": _NULL, "upper": _NULL},
                                    unit=blank_text(), value_text=blank_text()),
                _observation_schema({"value": _NUMBER, "lower": _NULL, "upper": _NULL},
                                    unit={"type": "string"}, value_text=non_empty_text()),
                _observation_schema({"value": {"type": ["number", "null"]}, "lower": _NUMBER, "upper": _NUMBER},
                                    unit={"type": "string"}, value_text=non_empty_text()),
            ]},
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
    published_at: str | None
    published_precision: str


@dataclass(frozen=True)
class Reading:
    """One source's observations, and how many quotes it offered that its source lacks.

    A quote counts when the excerpt does not contain it, and so does the wording of a
    number when its own quote does not.
    """
    observations: list[ReadObservation]
    unverified_quotes: int


def build_system_prompt(programme_context: str) -> str:
    return (
        "You read ONE source excerpt for ONE variable of an intervention target product profile "
        "(iTPP) that a team is drafting, and report what the excerpt says about that variable.\n\n"
        f"The profile is for this setting:\n{programme_context.strip()}\n"
        "Report what the excerpt says wherever it applies: the setting does not decide what you "
        "report. Where the excerpt says where or in whom something applies - the countries a "
        "product is licensed in, the programme a requirement serves, the population a result was "
        "in - keep that in measure, so a comparable product's market and population can be told "
        "apart from the setting and use the profile is for.\n\n"
        "Report two kinds of observation, and never mix them:\n"
        "- comparable_product: what an existing or investigational product achieved, showed or is "
        "specified to have for this variable. Name the product.\n"
        "- published_guidance: what a target product profile, guideline, prequalification or "
        "programme requirement asks of a product for this variable. Name the publisher as product.\n\n"
        "For each, copy the exact words from the excerpt that state it as quote, and say in measure "
        "what was measured or asked for. Give a number only as the excerpt writes it: value for a "
        "single figure, lower and upper for a range, the unit exactly as written, and in value_text "
        "the exact words of the quote that state the number. Leave the numbers null, and unit and "
        "value_text blank, for a statement in words. Report nothing when the excerpt does not speak "
        "to this variable for this disease."
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
    programme_context: str,
) -> Reading:
    """The source's observations; raises ``ModelResponseError`` when no reading came back.

    A reading whose quotes the excerpt lacks is repaired once. If the second reading still
    quotes words that are not there, its verified observations are kept and the rest counted.
    """
    excerpt = (finding.excerpt or "")[:MAX_EXCERPT_CHARS]
    message = (
        f"Product type: {intervention_term}. Disease / condition: {indication}.\n"
        f"Variable: {searchable_attribute_phrase(variable.name)}\n"
        f"What it covers: {variable.description.strip()}\n\n"
        f"Source: {finding.title}\nExcerpt:\n{excerpt}"
    )
    last: list[Reading] = []

    def parse(payload: dict | None) -> Reading:
        if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
            raise ValueError("no usable reading was returned")
        reading, missing, unstated = _reading(payload["observations"], finding, excerpt)
        last[:] = [reading]
        problems = []
        if missing:
            problems.append("these quotes are not in the excerpt word for word: "
                            + "; ".join(f'"{quote}"' for quote in missing))
        if unstated:
            problems.append("these value_text words are not in their own quote: "
                            + "; ".join(f'"{words}"' for words in unstated))
        if problems:
            raise ValueError(". ".join(problems))
        return reading

    try:
        return request_validated(
            llm_client, build_system_prompt(programme_context), message,
            schema_name="drafter_evidence_reading", schema=SCHEMA, max_tokens=MAX_TOKENS,
            task=TASK, effort=EFFORT,
            parse=parse, failure=f"Evidence reading failed for {variable.name} from {finding.url}",
            repair=lambda error: f"\n\nYour prior answer was not a usable reading: {error}. Answer again.",
        )
    except ModelResponseError:
        if last:
            return last[0]
        raise


def _reading(items: list, finding: Finding, excerpt: str) -> tuple[Reading, list[str], list[str]]:
    """The verified observations, the quotes the excerpt lacks, and the number wordings
    their quotes lack. An unverified wording keeps its observation, as words."""
    lane = finding.excerpt_source_lane or finding.source
    spec = {spec.key: spec for spec in source_specs()}.get(lane)
    lane_supplies_numbers = bool(spec and spec.excerpt_is_verbatim and spec.evidence_class in NUMERIC_EVIDENCE_CLASSES)
    label = finding.source_labels.get(lane) or (spec.label if spec else lane)
    observations: list[ReadObservation] = []
    missing: list[str] = []
    unstated: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("basis") not in BASES:
            raise ValueError("every observation names its basis")
        quote = " ".join(str(item.get("quote") or "").split())
        # Elision allowed: a reader quoting two sentences of one source joins them as a
        # quotation does, and each run is still checked word for word, in order. A number's
        # own words must sit inside one run, so no figure is set beside another sentence.
        if not quote_in_text(quote, excerpt, allow_elision=True):
            missing.append(quote)
            continue
        value = _value(item)
        if value is not None and not in_one_fragment(value.text, quote):
            unstated.append(value.text)
            value = None
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
            published_at=finding.published_at.date().isoformat() if finding.published_at else None,
            published_precision=finding.published_precision,
        ))
    return Reading(observations, len(missing) + len(unstated)), missing, unstated


def _value(item: dict) -> ObservedValue | None:
    """The stated number, or None for words. The schema fixes which fields each shape uses."""
    numbers = {key: item.get(key) for key in ("value", "lower", "upper")}
    if all(number is None for number in numbers.values()):
        return None
    if any(number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)))
           for number in numbers.values()):
        raise ValueError("an observation's numbers are numbers")
    return ObservedValue(
        value=float(numbers["value"]) if numbers["value"] is not None else None,
        lower=float(numbers["lower"]) if numbers["lower"] is not None else None,
        upper=float(numbers["upper"]) if numbers["upper"] is not None else None,
        unit=" ".join(str(item.get("unit") or "").split()),
        text=" ".join(str(item.get("value_text") or "").split()),
    )
