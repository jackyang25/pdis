"""Turn a document's own words for a value into the closed vocabulary a reader filters by.

Only the two filterable columns reach this stage. "Infants aged 6-14 weeks presenting for
EPI visits" is what the document says and what the corpus keeps; `infants` is what makes
it reachable from a picker, and the two are not interchangeable - the tag is a coarser
thing, chosen for navigation.

Separate from extraction, and the reason is re-runnability rather than tidiness. This
stage reads one short string, never the document, so when a tag vocabulary grows - someone
adds `neonates` - the whole corpus can be reclassified for the price of a few dozen cheap
calls. Folded into extraction, the same change would mean re-reading every document.

The stage is allowed to return nothing. A value that does not sit in the vocabulary gets
no tag, stays fully readable in `stated`, and shows up under an unfiltered view. Forcing
it into the nearest tag would be the failure this whole design is built to avoid: a filter
that quietly answers a question about `adults` with a row about health workers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared.ai import request_structured
from shared.batching import map_ordered
from shared.vocabulary import attribute_definitions

from services.archivist.indexed_attributes import indexed_attribute
from services.archivist.models import CorpusRecord

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 600
#: One value per request. Two populations in one prompt pull each other's reading.
VALUES_PER_REQUEST = 1
CLASSIFIER_WORKERS = 8


@dataclass
class ClassificationReport:
    """How many values were classified, and how many the vocabulary could not hold.

    `untagged` is the number worth watching. A vocabulary that leaves a third of its
    values untagged is too narrow, and that is visible here and nowhere else - in the
    corpus an untagged row is indistinguishable from one nobody tried to tag.
    """

    calls: int = 0
    tagged: int = 0
    untagged: int = 0
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "ClassificationReport") -> None:
        self.calls += other.calls
        self.tagged += other.tagged
        self.untagged += other.untagged
        self.notes.extend(other.notes)


def classification_schema(tags: tuple[str, ...]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["tags", "reason"],
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string", "enum": list(tags)},
            },
            "reason": {"type": "string"},
        },
    }


def build_system_prompt(attribute: str, description: str, tags: tuple[str, ...]) -> str:
    """Assemble the classification instructions for one filterable column."""
    local = attribute.split(".", 1)[1]
    return "\n".join(
        [
            f"You are filing one value under a fixed set of categories for the attribute "
            f"`{local}`.",
            "",
            "Return ONLY valid JSON. No markdown fences, no preamble.",
            "",
            f"WHAT THE ATTRIBUTE MEANS: {' '.join(description.split())}",
            "",
            "THE CATEGORIES, and nothing outside them:",
            "",
            *(f"- {tag}" for tag in tags),
            "",
            "Return every category the value genuinely falls under, and only those. A "
            "value can fall under several: a profile written for infants and pregnant "
            "women is both.",
            "",
            "Return an empty list when the value does not fall under any of them. That is "
            "an expected answer and a useful one. Do not reach for the closest category: "
            "these tags are what a reader filters by, and a value filed under the wrong "
            "one makes their results silently wrong, while an untagged value is still "
            "fully readable in the archive.",
            "",
            "Judge only the words you are given. Do not infer a category from what a "
            "profile of this kind usually targets.",
            "",
            "`reason`: one sentence on why, and say so plainly if nothing fits.",
        ]
    )


def classify_records(
    records: list[CorpusRecord],
    intervention_class: str,
    llm_client,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[CorpusRecord], ClassificationReport]:
    """Attach tags to every value of a filterable column, leaving other records alone.

    Returns a new list in the same order. Records are frozen, so a classified record is a
    replacement rather than a mutation - which also means a failed classification leaves
    the original row intact rather than half-written.
    """
    targets = [
        index
        for index, record in enumerate(records)
        if record.stated and _column_tags(intervention_class, record.attribute)
    ]
    if not targets or llm_client is None:
        return list(records), ClassificationReport()

    definitions = {d.name: d for d in attribute_definitions(intervention_class)}

    def classify(index: int):
        return _classify_one(
            records[index], intervention_class, definitions, llm_client, max_tokens
        )

    report = ClassificationReport()
    updated = list(records)
    for index, (tags, one_report) in zip(
        targets, map_ordered(targets, classify, workers=CLASSIFIER_WORKERS)
    ):
        report.merge(one_report)
        if tags:
            updated[index] = _with_tags(records[index], tags)
    return updated, report


def _column_tags(intervention_class: str, attribute: str) -> tuple[str, ...]:
    try:
        return indexed_attribute(intervention_class, attribute).tags
    except LookupError:
        return ()


def _with_tags(record: CorpusRecord, tags: tuple[str, ...]) -> CorpusRecord:
    from dataclasses import replace

    return replace(record, tags=tags)


def _classify_one(
    record: CorpusRecord,
    intervention_class: str,
    definitions: dict,
    llm_client,
    max_tokens: int,
) -> tuple[tuple[str, ...], ClassificationReport]:
    tags = _column_tags(intervention_class, record.attribute)
    report = ClassificationReport(calls=1)
    payload = request_structured(
        llm_client,
        build_system_prompt(
            record.attribute, definitions[record.attribute].description, tags
        ),
        # The value and the sentence it came from. The quote is included because a bare
        # value is often unfilable: "6-14 weeks" is an age band, a dosing interval, or a
        # window, and only the sentence around it says which.
        f"value: {record.stated}\n"
        f"the sentence it came from: {record.quote}\n\n"
        "File it now.",
        schema_name="archivist_value_tags",
        schema=classification_schema(tags),
        max_tokens=max_tokens,
        task="fast",
    )
    if not isinstance(payload, dict):
        report.untagged = 1
        report.notes.append(
            f"{record.document_id}/{record.attribute}: no answer from the classifier"
        )
        return (), report
    allowed = set(tags)
    chosen = tuple(
        dict.fromkeys(
            tag
            for tag in (str(value).strip() for value in payload.get("tags") or [])
            if tag in allowed
        )
    )
    if not chosen:
        report.untagged = 1
        return (), report
    report.tagged = 1
    return chosen, report
