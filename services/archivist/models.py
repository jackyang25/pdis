"""What the archive says, as data.

Archivist reports; it does not judge. Every other workspace tool holds a document to an
authority - a rubric, external evidence, another document, a question bank - and returns a
verdict. This one has no authority, so it has no verdict to return. Its corpus *is* the
authority, and the corpus is extracted rather than authored, which is why it has to be a
reviewed artifact rather than a runtime index: nobody should rely on "24 months, cited to
block b-0042" until a person has read that line and agreed with it.

Two collections, on two axes that never mix:

    documents   one entry per source file, exactly the header a run would pick
    records     one entry per document x attribute x bound x condition

Nothing is denormalized between them. A document's population tag is derivable from its
own records, and deriving it on read is the same rule the rest of the suite follows for
counts: a stored copy is a second authority that can disagree with the thing it came from.

Deliberately absent, and each absence is a decision:

    no score, grade, or ranking     there is no authority to grade against
    no comparison between records   two documents' values are shown, never reconciled
    no aggregate across source_type an iTPP target is a class-level ambition and a cTPP's
                                    is one candidate's commitment; a number blending them
                                    describes neither product
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from services.archivist.indexed_attributes import indexed_attributes
from shared.vocabulary import (
    attribute_definitions,
    indications_for,
    intervention_classes,
)

#: Whether the document answered, declined, or was unreadable on this attribute.
#:
#: `not_stated` is a first-class answer rather than an absent row. "Twelve comparable
#: profiles and none specified thermostability" is a finding in its own right - often the
#: most useful one when drafting from scratch - and it is only expressible if silence is
#: recorded. It also
#: keeps the model from filling a box: given no way to say nothing was stated, it states
#: something.
#:
#: `uncertain` is the gap the verbatim check cannot close. A quote that really appears in
#: the block can still be the wrong sentence for this attribute - a storage temperature
#: read as a shelf life. So the reading is kept, flagged, and reviewed rather than either
#: trusted or thrown away. It is the one status that may carry a value or no value: the
#: doubt can be about which sentence answers the attribute, or about whether any does.
RECORD_STATUSES = frozenset({"stated", "not_stated", "uncertain"})

#: Which column of the profile's template the value came from.
#:
#: TPP templates state a minimum and an optimistic target side by side, so one attribute
#: yields two values that mean different things. `single` is for an attribute the document
#: states once, which is not the same as stating it as a minimum.
VALUE_BOUNDS = frozenset({"minimum", "optimal", "single"})



@dataclass(frozen=True)
class CorpusDocument:
    """One source file, described exactly as a run would describe it.

    The four fields are the shared header every tool already asks for, declared per file
    instead of picked per run. Nothing is inferred: `source_type` in particular is read
    off a cover page by a person, because it is the one field whose error is silent - mix
    an iTPP with a cTPP and every value below blends an ambition with a commitment, and no
    downstream check would notice.
    """

    id: str
    title: str
    org: str
    intervention_class: str
    indication: str
    source_type: str

    def __post_init__(self) -> None:
        for name in ("id", "title", "org", "intervention_class", "indication", "source_type"):
            object.__setattr__(self, name, " ".join(str(getattr(self, name)).split()))
        if not self.id or not self.title:
            raise ValueError("a corpus document needs an id and a title")
        if self.intervention_class not in intervention_classes():
            raise ValueError(
                f"{self.id}: unknown intervention class {self.intervention_class!r}"
            )
        if self.indication not in indications_for(self.intervention_class):
            raise ValueError(
                f"{self.id}: {self.indication!r} is not an indication declared for "
                f"{self.intervention_class}"
            )


@dataclass(frozen=True)
class CorpusRecord:
    """One thing one document said about one attribute.

    The field groups are three planes, and a value from one never lands in another:

        what question   attribute, bound, condition_attribute, condition_stated
        what answer     status, stated, magnitude, unit, tags
        where it came   quote, block_id, block_text, section_label
      from

    `stated` is the document's own words for the value. `quote` is the sentence that
    proves it, and `stated` is a span of it. `block_text` is the block the sentence sits
    in, and it is carried because a bare quote misleads: "24 months" reads differently
    when the same block says "for the lyophilized presentation only". Nested, not
    overlapping.

    `magnitude` and `unit` are parsed from `stated` in code, never asked of a model - a
    number a model retyped is a number that can differ from the document's. They exist so
    identical answers group; they are absent whenever `stated` is not a clean quantity,
    which is most of `presentation`.
    """

    document_id: str
    attribute: str
    status: str
    bound: str = "single"
    #: The attribute this value is conditional on, when the document states one value per
    #: presentation, population, or market. Typed rather than a free-text note, because a
    #: note accepts anything and two documents will phrase the same condition differently.
    condition_attribute: str = ""
    condition_stated: str = ""
    stated: str = ""
    magnitude: float | None = None
    unit: str = ""
    #: Closed-vocabulary values for the attributes a reader filters by. Empty for every
    #: other attribute. The document's own words stay in `stated`; this is the short form
    #: that makes "infants aged 6-14 weeks" reachable from a picker.
    tags: tuple[str, ...] = ()
    quote: str = ""
    block_id: str = ""
    block_text: str = ""
    #: The citing block's own section label, as chunker's mapper assigned it. Carried
    #: rather than a separate "was this where we expected it" flag: attributes declare no
    #: section anywhere in the suite, so any such flag would need an invented
    #: attribute-to-section map per document type. This is the same information, already
    #: on the block, and it cannot go stale.
    section_label: str = ""
    #: Why the document was read as saying nothing, or why the reading is uncertain. Never
    #: set on a `stated` record, where the quote is the justification. This is review
    #: material - "the section gives a storage temperature but no shelf life" is what tells
    #: a reviewer whether to trust the silence - and it is never filtered or compared.
    reason: str = ""

    def __post_init__(self) -> None:
        for name in ("document_id", "attribute", "status", "bound", "condition_attribute",
                     "condition_stated", "stated", "unit", "quote", "block_id",
                     "block_text", "section_label", "reason"):
            object.__setattr__(self, name, " ".join(str(getattr(self, name)).split()))
        object.__setattr__(self, "tags", tuple(dict.fromkeys(self.tags)))
        if not self.document_id or not self.attribute:
            raise ValueError("a record needs a document and an attribute")
        if self.status not in RECORD_STATUSES:
            raise ValueError(f"{self.attribute}: unknown status {self.status!r}")
        if self.bound not in VALUE_BOUNDS:
            raise ValueError(f"{self.attribute}: unknown bound {self.bound!r}")
        if self.status == "stated" and not self.stated:
            raise ValueError(f"{self.attribute}: a stated record needs a value")
        if self.status == "not_stated" and self.stated:
            raise ValueError(
                f"{self.attribute}: a not_stated record carries no value"
            )
        if self.status == "stated" and self.reason:
            # A stated value is justified by its quote. A prose reason beside it would be
            # a second, unverifiable justification competing with the first.
            raise ValueError(
                f"{self.attribute}: a stated record explains itself with its quote"
            )
        if not self.stated:
            if self.quote or self.tags or self.magnitude is not None:
                raise ValueError(
                    f"{self.attribute}: a record with no value carries no quote, no tags "
                    "and no magnitude"
                )
            return
        self._check_provenance_chain()
        if bool(self.condition_attribute) != bool(self.condition_stated):
            raise ValueError(
                f"{self.attribute}: a condition needs both an attribute and the "
                "document's words for it"
            )
        if self.condition_stated and self.condition_stated not in self.block_text:
            raise ValueError(
                f"{self.attribute}: the condition is not stated in the block it cites"
            )
        if self.magnitude is not None and not self.unit:
            raise ValueError(f"{self.attribute}: a magnitude with no unit measures nothing")

    def _check_provenance_chain(self) -> None:
        """`stated` sits inside `quote`, which sits inside `block_text`.

        The chain is what makes the corpus unfalsifiable rather than merely well-reviewed.
        Each link closes a different failure:

        - `quote` inside `block_text` rules out a fabricated sentence.
        - `stated` inside `quote` rules out a paraphrase. A model asked for a shelf life
          will happily answer "about two years" from a document that said "24 months",
          and the two are not interchangeable when the archive is quoted back to a
          partner.

        Enforced here rather than only at extraction so a hand-edited artifact cannot
        introduce what the build would have rejected.
        """
        if not self.quote or not self.block_id:
            raise ValueError(
                f"{self.attribute}: a value with no quote and block is a value nobody "
                "can check"
            )
        if self.quote not in self.block_text:
            raise ValueError(
                f"{self.attribute}: the quote does not appear in the block it cites"
            )
        if self.stated not in self.quote:
            raise ValueError(
                f"{self.attribute}: the value {self.stated!r} is not a span of the quote "
                "that is supposed to prove it"
            )


@dataclass(frozen=True)
class Corpus:
    """The reviewed archive: its documents, its records, and how it was built."""

    documents: tuple[CorpusDocument, ...] = ()
    records: tuple[CorpusRecord, ...] = ()
    built_at: str = ""

    def __post_init__(self) -> None:
        ids = [document.id for document in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("the corpus lists a document twice")
        unknown = sorted({r.document_id for r in self.records} - set(ids))
        if unknown:
            raise ValueError(f"records cite documents the corpus does not list: {unknown}")
        self._check_columns()
        self._check_exhaustive()
        self._check_unique()

    def _check_columns(self) -> None:
        """Every record answers a declared column, in that column's own vocabulary.

        Here rather than on `CorpusRecord` because none of it is checkable from a record
        alone: which columns exist, which tags are allowed, and which attributes a
        condition may name all follow from the document's intervention class.
        """
        columns_by_class: dict[str, dict] = {}
        siblings_by_class: dict[str, set[str]] = {}
        for record in self.records:
            document = self.document(record.document_id)
            columns = columns_by_class.setdefault(
                document.intervention_class,
                {c.attribute: c for c in indexed_attributes(document.intervention_class)},
            )
            column = columns.get(record.attribute)
            if column is None:
                raise ValueError(
                    f"{record.document_id}: {record.attribute!r} is not a corpus column "
                    f"for {document.intervention_class}"
                )
            allowed = set(column.tags)
            stray = sorted(set(record.tags) - allowed)
            if stray:
                raise ValueError(
                    f"{record.document_id}/{record.attribute}: tags outside the declared "
                    f"vocabulary: {stray}"
                )
            if record.magnitude is not None and not column.quantity:
                raise ValueError(
                    f"{record.document_id}/{record.attribute}: a magnitude was parsed for "
                    "a column that declares no quantity"
                )
            if record.condition_attribute:
                siblings = siblings_by_class.setdefault(
                    document.intervention_class,
                    {
                        definition.name
                        for definition in attribute_definitions(document.intervention_class)
                    },
                )
                if record.condition_attribute not in siblings:
                    raise ValueError(
                        f"{record.document_id}/{record.attribute}: conditional on "
                        f"{record.condition_attribute!r}, which is not an attribute of "
                        f"{document.intervention_class}"
                    )

    def _check_exhaustive(self) -> None:
        """Every document answers every column of its class, even to decline.

        The corpus is a grid, not a list of hits. "Eleven of twelve profiles never
        specified thermostability" is the most useful thing an archive can say when
        drafting from scratch, and it is only sayable if silence is a row. A sparse corpus
        makes that question unanswerable without knowing which documents were even read.
        """
        present = {(r.document_id, r.attribute) for r in self.records}
        missing = [
            f"{document.id}/{column.attribute}"
            for document in self.documents
            for column in indexed_attributes(document.intervention_class)
            if (document.id, column.attribute) not in present
        ]
        if missing:
            raise ValueError(
                f"the corpus is sparse - no row at all for: {sorted(missing)[:5]}"
                + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
            )

    def _check_unique(self) -> None:
        """One row per question asked. The key is what makes two values not duplicates."""
        keys: dict[tuple[str, ...], int] = {}
        for record in self.records:
            key = (
                record.document_id,
                record.attribute,
                record.bound,
                record.condition_attribute,
                record.condition_stated,
            )
            keys[key] = keys.get(key, 0) + 1
        duplicated = sorted(k for k, count in keys.items() if count > 1)
        if duplicated:
            raise ValueError(f"two records answer the same question: {duplicated[0]}")

    def document(self, document_id: str) -> CorpusDocument:
        for document in self.documents:
            if document.id == document_id:
                return document
        raise KeyError(document_id)


def records_for(records: Iterable[CorpusRecord], attribute: str) -> list[CorpusRecord]:
    """Every record for one attribute, in corpus order."""
    return [record for record in records if record.attribute == attribute]
