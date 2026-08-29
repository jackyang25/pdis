"""Exact document quotation, and the one rule that makes it trustworthy.

A citation that names a block says *where* a claim came from. A citation that carries
the sentence says *what* was read, and it is the second one a reader can check without
opening anything: the difference between highlighting a 400-word table and underlining
the row the number is in.

The rule this module exists to hold is that **a model never retypes source text**. It
selects a line range - a block ID and two integers - and `selected_source_lines` copies
those lines out of the block. A model asked to quote will paraphrase, normalise a unit,
or fix a typo, and the result is a quotation that appears in no document; it cannot do
that with a range, because the range is not the text.

Scout had all of this and Aligner had none of it, so Aligner's trace highlighted a whole
block where Scout underlined a line. Two services wanting one guarantee is what `shared`
is for, and the guarantee is the part that must not be reimplemented: a second copy is a
second chance to start trusting text the model typed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

#: What to tell a model that must cite source lines. One wording, because a producer and
#: its validator disagreeing about the wire shape is the failure this prevents.
LINE_SPAN_JSON_INSTRUCTION = (
    "Document text lines are labeled [line:N] within each [block:<id>]. For every "
    "source span, select one complete bare block_id plus inclusive start_line and "
    "end_line values exactly as displayed. Do not retype or paraphrase source text; "
    "deterministic code will copy the selected lines from the original block."
)


@dataclass
class DocumentSpan:
    """One exact document quotation supporting a canonical document fact."""

    quote: str
    block_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.quote = " ".join(self.quote.split())
        self.block_ids = list(dict.fromkeys(self.block_ids))
        if not self.quote or not self.block_ids:
            raise ValueError("document span requires a quote and block IDs")


def line_addressable(content: str) -> str:
    """Label physical source lines without changing their canonical text.

    A wire view only. The labels let a model point at a passage; they are never part of
    the text that comes back, because nothing that comes back is text.
    """
    return "\n".join(
        f"[line:{index}] {line}"
        for index, line in enumerate(content.splitlines(), 1)
    )


def selected_source_lines(
    raw_span: object,
    source_blocks: dict[str, str],
) -> tuple[str, str] | None:
    """Resolve one model-selected line range to exact canonical source text.

    `None` for anything that does not resolve - an unknown block, a reversed range, a
    range running off the end, an empty selection. Callers turn that into their own
    contract error, because what an unresolvable citation means differs by service.
    """
    if not isinstance(raw_span, dict):
        return None
    block_id = str(raw_span.get("block_id", "")).strip()
    if block_id not in source_blocks:
        return None
    start_line = raw_span.get("start_line")
    end_line = raw_span.get("end_line")
    if (
        isinstance(start_line, bool)
        or isinstance(end_line, bool)
        or not isinstance(start_line, int)
        or not isinstance(end_line, int)
    ):
        return None
    lines = source_blocks[block_id].splitlines()
    if not (1 <= start_line <= end_line <= len(lines)):
        return None
    quote = "\n".join(lines[start_line - 1:end_line]).strip()
    if not quote:
        return None
    return quote, block_id


def resolved_spans(
    raw: object,
    source_blocks: dict[str, str],
) -> list[DocumentSpan]:
    """Every selected range that resolves, as the text it actually points at.

    A range that does not resolve is dropped rather than repaired, and the same passage
    selected twice is kept once. What an empty result *means* is the caller's to decide:
    for a verdict that must be cited it is a contract failure, and for one asserting
    silence it is the expected answer.
    """
    if not isinstance(raw, list):
        return []
    spans: list[DocumentSpan] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        selected = selected_source_lines(item, source_blocks)
        if selected is None:
            continue
        quote, block_id = selected
        if (block_id, quote) in seen:
            continue
        seen.add((block_id, quote))
        spans.append(DocumentSpan(quote=quote, block_ids=[block_id]))
    return spans


def line_span_schema(block_ids: Sequence[str]) -> dict[str, object]:
    """The closed wire shape of one selected range.

    `block_id` is an enum of the blocks actually supplied, so a citation to a document
    that was never shown is unrepresentable rather than merely invalid.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["block_id", "start_line", "end_line"],
        "properties": {
            "block_id": {"type": "string", "enum": list(block_ids)},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
    }


def span_block_ids(spans: Iterable[DocumentSpan]) -> list[str]:
    """Every block a set of spans reaches, in order, once each.

    Derived rather than stored. A finding carrying both its spans and a block list has
    one fact in two fields, and the two can disagree - which is exactly the state the
    reader is trusting the citation not to be in.
    """
    seen: dict[str, None] = {}
    for span in spans:
        for block_id in span.block_ids:
            seen.setdefault(block_id, None)
    return list(seen)
