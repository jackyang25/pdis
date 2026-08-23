"""Read one attribute out of one document, or record that the document is silent.

One model call per (document, attribute). Not one call per document asking for all eight,
because these are eight independent readings and a single prompt makes them influence each
other: a model that has just found a shelf life is measurably readier to read the next
sentence as a thermostability regime. The suite applies this rule wherever a decision is
per item, and each column of the corpus is a per-item decision.

The model is given a narrow job and almost no room to be creative:

    it decides    whether the document states this attribute, in which words, under
                  which bound, and subject to which condition
    it never      normalises a number, converts a unit, names a block, resolves a tag, or
                  compares one document with another

Everything in the second list is either parsed in code from the model's own quoted words
or decided by a later stage. `block_id` in particular is *found* rather than asked for:
the model returns a verbatim quote, and code locates the block containing it. A model
asked for both can return a quote from one block and the id of another, and nothing
downstream could tell which half was wrong.

**Why the document comes first in the request.** The eight calls for one document differ
only in their last few hundred words. Putting the constant part first - the reading rules
in the system prompt, then the document - makes the eight share a cacheable prefix, so a
document is charged as new input once rather than eight times. The attribute's own
definition and its fence go last, which is also where a final instruction reads most
strongly.

Silence is a real answer here. Most documents do not state most attributes, and a corpus
that omits those rows cannot answer "how many of our profiles ever specified this", which
is the question an archive exists to answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared.ai import request_structured
from shared.batching import map_ordered
from shared.vocabulary import AttributeDefinition, attribute_definitions

from services.archivist.indexed_attributes import IndexedAttribute, indexed_attributes
from services.archivist.models import (
    RECORD_STATUSES,
    VALUE_BOUNDS,
    CorpusDocument,
    CorpusRecord,
)
from services.archivist.quantity import parse_quantity

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 2000
#: One attribute per request; see the module docstring.
ATTRIBUTES_PER_REQUEST = 1
#: Blocks are sent whole, in order, until this budget is spent. A truncated block would
#: still verify correctly - verification runs against the full block text - so overrunning
#: costs recall rather than correctness, and it logs.
MAX_DOCUMENT_CHARS = 200_000

#: Bounds in the order a TPP table prints them, for the prompt.
BOUND_ORDER = ("minimum", "optimal", "single")


@dataclass
class ExtractionReport:
    """What the extraction did, for the build report.

    Counted rather than derived from the records: a reading discarded because its quote
    was not in the document leaves no record behind, so the corpus alone cannot say
    whether a document was read badly or was genuinely silent. `unverified` and
    `paraphrased` are the two numbers that say whether a build is trustworthy at all, and
    neither is visible in the artifact.
    """

    calls: int = 0
    unanswered: int = 0
    silent: int = 0
    uncertain: int = 0
    unverified: int = 0
    paraphrased: int = 0
    #: Deliberately no `values` counter. How many values a build kept is a fact about the
    #: corpus, and the corpus is the artifact - counting it here as well would be a second
    #: authority on the same number. The counters that remain are the ones the corpus
    #: cannot answer, because a discarded reading leaves no row behind.
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "ExtractionReport") -> None:
        self.calls += other.calls
        self.unanswered += other.unanswered
        self.silent += other.silent
        self.uncertain += other.uncertain
        self.unverified += other.unverified
        self.paraphrased += other.paraphrased
        self.notes.extend(other.notes)


@dataclass(frozen=True)
class PreparedDocument:
    """A document rendered once, ready for every attribute call against it.

    The unit of parallelism is (prepared document, column), which lets the build run one
    flat pool over every pair rather than nesting a pool over attributes inside a pool
    over documents. Nested pools multiply into a concurrency nobody declared.
    """

    document: CorpusDocument
    text: str
    blocks_by_id: dict
    definitions: dict[str, AttributeDefinition]

    def columns(self) -> tuple[IndexedAttribute, ...]:
        return indexed_attributes(self.document.intervention_class)


def extraction_schema(intervention_class: str) -> dict[str, object]:
    """The wire contract for one attribute reading.

    `condition_attribute` is enumerated over every attribute of the class rather than a
    hand-picked shortlist. The shortlist would be invented content in a file that reads
    like a declaration, and `Corpus` validates against the same full set, so enumerating
    it here keeps one vocabulary on both ends of the wire.
    """
    conditions = [""] + [d.name for d in attribute_definitions(intervention_class)]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "reason", "values"],
        "properties": {
            "status": {"type": "string", "enum": sorted(RECORD_STATUSES)},
            "reason": {"type": "string"},
            "values": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "bound",
                        "stated",
                        "quote",
                        "condition_attribute",
                        "condition_stated",
                    ],
                    "properties": {
                        "bound": {"type": "string", "enum": list(BOUND_ORDER)},
                        "stated": {"type": "string"},
                        "quote": {"type": "string"},
                        "condition_attribute": {"type": "string", "enum": conditions},
                        "condition_stated": {"type": "string"},
                    },
                },
            },
        },
    }


def build_system_prompt() -> str:
    """The reading rules, identical for every attribute and every document.

    Constant on purpose: it is the head of the cacheable prefix, and it is also the half
    of the instructions that must not drift between columns. Which attribute is being read
    arrives at the end of the user message, in `build_attribute_instructions`.
    """
    return "\n".join(
        [
            "You are reading one target product profile to find what it says about "
            "exactly one attribute. The document comes first, then the attribute.",
            "",
            "Return ONLY valid JSON. No markdown fences, no preamble.",
            "",
            "STATUS",
            "",
            '"stated" - the document gives a value for the attribute.',
            '"not_stated" - it does not. This is a common and correct answer. Most '
            "profiles leave most attributes unspecified, and recording that is the point: "
            "an archive has to be able to say how many profiles never specified "
            "something.",
            '"uncertain" - you found something that may be this attribute and may be one '
            "of the neighbouring attributes named at the end. Return it as a value and "
            "say why in `reason`. Do not resolve the doubt by guessing; a flagged reading "
            "gets reviewed, a confident wrong one does not.",
            "",
            "VALUES",
            "",
            "One entry per distinct value the document gives. Usually one. Two when the "
            "document prints a minimum and an optimal target side by side, which these "
            "profiles routinely do in a two-column table. More when the value differs by "
            "condition.",
            "",
            '`bound`: "minimum" for a threshold, floor, or minimally acceptable target. '
            '"optimal" for a preferred, optimistic, or stretch target. "single" when the '
            "document states one value without framing it as either. Do not infer a bound "
            "from whether a number looks ambitious.",
            "",
            "`stated`: the document's own words for the value, copied exactly. Not "
            "normalised, not converted, not rounded. If the document says \"at least 24 "
            'months" then that is the value; do not write "2 years" or "24".',
            "",
            "`quote`: a span copied character-for-character from one block of the "
            "document, long enough to contain `stated` and to show what it refers to. "
            "`stated` must appear inside `quote` exactly. Both are checked against the "
            "document afterwards, and a value whose quote is not found verbatim is "
            "discarded, so a paraphrase loses the reading entirely.",
            "",
            "`condition_attribute` and `condition_stated`: fill both only when the "
            "document makes this value conditional on something else - one shelf life for "
            "the lyophilized presentation and another for the liquid, one price for one "
            "market. `condition_attribute` names the attribute the condition is about, "
            "and `condition_stated` copies the document's words for it. Leave both empty "
            "otherwise, which is the usual case. Never use them for a general caveat.",
            "",
            '`reason`: one sentence, only for "not_stated" and "uncertain". Say what the '
            "document does have where you looked, so a reviewer can judge the silence.",
            "",
            "You are not assessing whether the target is reasonable, comparing it with "
            "anything, or filling a gap from what a profile like this usually says. If it "
            "is not in the text, it is not stated.",
        ]
    )


def build_attribute_instructions(
    column: IndexedAttribute,
    definitions: dict[str, AttributeDefinition],
) -> str:
    """Which attribute to read, and the fence around it.

    The fence is built from the shared vocabulary's own words - for the attribute and for
    each sibling it is not. Naming the siblings rather than describing the boundary in
    prose is what keeps this from going stale: a renamed attribute fails a test instead of
    leaving a sentence about a field that no longer exists.
    """
    definition = definitions[column.attribute]
    lines = [
        f"THE ATTRIBUTE TO READ: {column.local_name}",
        "",
        " ".join(definition.description.split()),
    ]
    if column.not_confused_with:
        lines += [
            "",
            "WHAT THIS ATTRIBUTE IS NOT",
            "",
            "Each of the following is a separate attribute, recorded separately. A value "
            "belonging to one of them is not an answer here, however close it sits on the "
            "page. If the document states one of these and not the attribute above, the "
            'answer is "not_stated".',
            "",
        ]
        for sibling in column.not_confused_with:
            lines.append(
                f"- {sibling.split('.', 1)[1]}: "
                f"{' '.join(definitions[sibling].description.split())}"
            )
    lines += ["", f"Read `{column.local_name}` now."]
    return "\n".join(lines)


def build_document_text(blocks: list) -> str:
    """The document, as addressable blocks.

    Every block carries its section label and heading path, and that is not decoration:
    in these profiles the value often lives in a table row that reads "24 months | 36
    months" and nothing else. Without the row's heading the bound is unanswerable, and
    without the section the attribute is unidentifiable.
    """
    lines: list[str] = []
    budget = MAX_DOCUMENT_CHARS
    dropped = 0
    for block in blocks:
        content = " ".join((block.content or "").split())
        if not content:
            continue
        context = " > ".join(part for part in (block.heading_stack or []) if part)
        header = f"[{block.id}]"
        if block.section_label:
            header += f" section: {block.section_label}"
        if context:
            header += f" | under: {context}"
        entry = f"{header}\n{content}"
        if len(entry) > budget:
            dropped += 1
            continue
        budget -= len(entry)
        lines.append(entry)
    if dropped:
        logger.warning(
            "Document exceeded the prompt budget; %d blocks were not sent", dropped
        )
    return "\n\n".join(lines)


def prepare_document(document: CorpusDocument, blocks: list) -> PreparedDocument:
    """Render one document once, for every attribute call against it."""
    return PreparedDocument(
        document=document,
        text=build_document_text(blocks),
        blocks_by_id={block.id: block for block in blocks},
        definitions={
            definition.name: definition
            for definition in attribute_definitions(document.intervention_class)
        },
    )


def extract_attribute(
    prepared: PreparedDocument,
    column: IndexedAttribute,
    llm_client,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[list[CorpusRecord], ExtractionReport]:
    """Read one attribute of one document. Always returns at least one record.

    A column the model failed to answer at all becomes an `uncertain` row naming the
    failure rather than a missing row, because the corpus is a grid: a hole in it would
    read as "the document is silent" and mean "we never found out".
    """
    document = prepared.document
    report = ExtractionReport(calls=1)
    payload = request_structured(
        llm_client,
        build_system_prompt(),
        f"{prepared.text}\n\n{build_attribute_instructions(column, prepared.definitions)}",
        schema_name="archivist_attribute_reading",
        schema=extraction_schema(document.intervention_class),
        max_tokens=max_tokens,
        task="reasoning",
    )
    if not isinstance(payload, dict):
        report.unanswered = 1
        report.notes.append(f"{document.id}/{column.local_name}: no answer from the model")
        return [_flagged(document, column, "The model returned no reading.")], report

    status = str(payload.get("status") or "").strip().lower()
    if status not in RECORD_STATUSES:
        # The schema enumerates it, so this is a malformed answer rather than a judgment.
        # Reading it as `stated` would promote a broken response to a fact.
        status = "uncertain"
    reason = " ".join(str(payload.get("reason") or "").split())
    raw_values = payload.get("values")
    raw_values = raw_values if isinstance(raw_values, list) else []

    if status == "not_stated" or (status == "stated" and not raw_values):
        report.silent = 1
        return (
            [
                CorpusRecord(
                    document_id=document.id,
                    attribute=column.attribute,
                    status="not_stated",
                    reason=reason,
                )
            ],
            report,
        )

    records: list[CorpusRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_values:
        if not isinstance(raw, dict):
            continue
        record = _build_record(prepared, column, status, reason, raw, report)
        if record is None:
            continue
        key = (record.bound, record.condition_attribute, record.condition_stated)
        if key in seen:
            # Two readings of the same question. The second is not a second value; it is
            # the same slot answered twice, and `Corpus` would refuse the pair.
            report.notes.append(
                f"{document.id}/{column.local_name}: dropped a repeat reading of "
                f"{record.bound}"
            )
            continue
        seen.add(key)
        records.append(record)

    if not records:
        report.uncertain = 1
        return (
            [
                _flagged(
                    document,
                    column,
                    reason
                    or "A reading was offered but none of it could be verified against "
                    "the document.",
                )
            ],
            report,
        )
    report.uncertain = sum(1 for record in records if record.status == "uncertain")
    return records, report


def extract_document(
    document: CorpusDocument,
    blocks: list,
    llm_client,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    workers: int = 8,
) -> tuple[list[CorpusRecord], ExtractionReport]:
    """Read every corpus column of one document.

    A convenience wrapper over `extract_attribute`. The build does not use it: it pools
    over every (document, column) pair at once, which is the same work without a pool
    inside a pool.
    """
    prepared = prepare_document(document, blocks)

    def read(column: IndexedAttribute):
        return extract_attribute(prepared, column, llm_client, max_tokens=max_tokens)

    report = ExtractionReport()
    records: list[CorpusRecord] = []
    for column_records, column_report in map_ordered(
        list(prepared.columns()), read, workers=workers
    ):
        records.extend(column_records)
        report.merge(column_report)
    return records, report


def _flagged(document: CorpusDocument, column: IndexedAttribute, reason: str) -> CorpusRecord:
    return CorpusRecord(
        document_id=document.id,
        attribute=column.attribute,
        status="uncertain",
        reason=reason,
    )


def _build_record(
    prepared: PreparedDocument,
    column: IndexedAttribute,
    status: str,
    reason: str,
    raw: dict,
    report: ExtractionReport,
) -> CorpusRecord | None:
    """Verify one offered value against the document, or discard it.

    Discarding is the point. Every check here fails closed: an unverifiable reading
    leaves no row, and the caller turns "no rows survived" into a flagged `uncertain`
    row. That is a worse outcome for recall and the only safe one for a corpus that gets
    quoted back to partners.
    """
    document = prepared.document
    stated = " ".join(str(raw.get("stated") or "").split())
    quote = " ".join(str(raw.get("quote") or "").split())
    if not stated or not quote:
        return None

    block = _find_block(quote, prepared.blocks_by_id)
    if block is None:
        report.unverified += 1
        report.notes.append(
            f"{document.id}/{column.local_name}: quote not found in any block - "
            f"{quote[:60]!r}"
        )
        return None
    if stated not in quote:
        report.paraphrased += 1
        report.notes.append(
            f"{document.id}/{column.local_name}: {stated!r} is not a span of its own quote"
        )
        return None

    bound = str(raw.get("bound") or "single").strip().lower()
    if bound not in VALUE_BOUNDS:
        bound = "single"
    block_text = " ".join((block.content or "").split())
    condition_attribute = " ".join(str(raw.get("condition_attribute") or "").split())
    condition_stated = " ".join(str(raw.get("condition_stated") or "").split())
    if not condition_attribute or not condition_stated:
        # Half a condition is not a condition. Dropping both is right rather than
        # inventing the missing half, and the value itself is unaffected.
        condition_attribute = condition_stated = ""
    elif condition_attribute not in prepared.definitions:
        report.notes.append(
            f"{document.id}/{column.local_name}: condition named "
            f"{condition_attribute!r}, which is not an attribute of "
            f"{document.intervention_class}; kept the value, dropped the condition"
        )
        condition_attribute = condition_stated = ""
    elif condition_stated not in block_text:
        report.notes.append(
            f"{document.id}/{column.local_name}: the condition {condition_stated!r} is "
            "not in the citing block; kept the value, dropped the condition"
        )
        condition_attribute = condition_stated = ""

    magnitude, unit = parse_quantity(stated, column.quantity)
    return CorpusRecord(
        document_id=document.id,
        attribute=column.attribute,
        status="uncertain" if status == "uncertain" else "stated",
        bound=bound,
        condition_attribute=condition_attribute,
        condition_stated=condition_stated,
        stated=stated,
        magnitude=magnitude,
        unit=unit,
        quote=quote,
        block_id=block.id,
        block_text=block_text,
        section_label=block.section_label or "",
        # The doubt is about the reading, and the status is per call, so the call's own
        # one-sentence reason explains every value it produced.
        reason=reason if status == "uncertain" else "",
    )


def _find_block(quote: str, blocks_by_id: dict):
    """The first block whose text contains the quote, in document order.

    Derived rather than asked for. Two blocks containing the identical sentence both
    support the value, so taking the first is truthful and deterministic; asking the
    model for the id instead admits a quote and an id that disagree.
    """
    for block in blocks_by_id.values():
        if quote and quote in " ".join((block.content or "").split()):
            return block
    return None
