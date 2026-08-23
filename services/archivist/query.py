"""Read the corpus. A filter and a grouping, and no model call anywhere.

Archivist reports what the archive says. It does not judge, so there is nothing here for a
model to decide: the answer to "what have our vaccine profiles required for shelf life" is
a selection of rows, and a selection is arithmetic. The same question routed through a
model would produce a fluent summary that no longer matches any row, which is the one
thing an archive must not do.

Three shapes stack, on three axes that never mix:

    the attribute   what was asked about. One group per column.
    the source type how the answers must be kept apart. An iTPP states a class-level
                    ambition and a cTPP states one candidate's commitment; a list mixing
                    them describes neither product, so they are separate groups and there
                    is no representation in which they are one.
    the state       whether the document answered, declined, or was unclear. Three
                    disjoint lists, because a count is only meaningful if it is obvious
                    which of the three it counted.

Counts are properties, not fields. "Three of twelve profiles specified this" is derived
from the lists it describes, so it cannot disagree with them - the same rule the rest of
the suite follows for anything a reader could recompute.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.archivist.indexed_attributes import indexed_attributes
from services.archivist.models import Corpus, CorpusDocument, CorpusRecord


@dataclass(frozen=True)
class TagFilter:
    """One filterable column narrowed to a set of tags.

    Any of the tags matches (a reader asking for infants and children wants either), and
    every filter must match (a reader asking for infants *and* outbreak response wants
    both). Stated here rather than left to the caller because the two rules are not
    interchangeable and a reader cannot see which one an interface chose.
    """

    attribute: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorpusQuery:
    """What to read out of the corpus.

    `intervention_class` is required and is not a filter like the others: the columns
    themselves are declared per class, so it decides what the answer can even be about.
    Everything else narrows a set of documents.
    """

    intervention_class: str
    attributes: tuple[str, ...] = ()
    indications: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    orgs: tuple[str, ...] = ()
    tags: tuple[TagFilter, ...] = ()

    def __post_init__(self) -> None:
        columns = {column.attribute for column in indexed_attributes(self.intervention_class)}
        unknown = sorted(set(self.attributes) - columns)
        if unknown:
            raise ValueError(
                f"not corpus columns for {self.intervention_class}: {unknown}"
            )
        by_attribute = {
            column.attribute: column
            for column in indexed_attributes(self.intervention_class)
        }
        for tag_filter in self.tags:
            column = by_attribute.get(tag_filter.attribute)
            if column is None:
                raise ValueError(
                    f"cannot filter on {tag_filter.attribute!r}: not a corpus column"
                )
            if not column.filterable:
                raise ValueError(
                    f"cannot filter on {tag_filter.attribute!r}: it is read, not "
                    "filtered. Only a column declaring a closed tag vocabulary can be "
                    "filtered, because only those have a fixed set of answers."
                )
            stray = sorted(set(tag_filter.values) - set(column.tags))
            if stray:
                raise ValueError(
                    f"{tag_filter.attribute}: not declared tags: {stray}"
                )

    def columns(self) -> tuple[str, ...]:
        """The columns to answer, in declaration order. Empty means every column."""
        declared = [column.attribute for column in indexed_attributes(self.intervention_class)]
        if not self.attributes:
            return tuple(declared)
        wanted = set(self.attributes)
        return tuple(attribute for attribute in declared if attribute in wanted)


@dataclass(frozen=True)
class SourceTypeGroup:
    """One document type's answers for one column, in three disjoint states."""

    source_type: str
    values: tuple[CorpusRecord, ...] = ()
    uncertain: tuple[CorpusRecord, ...] = ()
    silent: tuple[str, ...] = ()

    @property
    def documents_answering(self) -> int:
        return len({record.document_id for record in self.values})

    @property
    def documents_total(self) -> int:
        return len(
            {record.document_id for record in self.values + self.uncertain}
            | set(self.silent)
        )


@dataclass(frozen=True)
class AttributeGroup:
    """Every answer to one column, kept apart by document type."""

    attribute: str
    quantity: str = ""
    tag_vocabulary: tuple[str, ...] = ()
    groups: tuple[SourceTypeGroup, ...] = ()

    @property
    def documents_answering(self) -> int:
        return sum(group.documents_answering for group in self.groups)

    @property
    def documents_total(self) -> int:
        return sum(group.documents_total for group in self.groups)


@dataclass(frozen=True)
class CorpusAnswer:
    """What the archive says, for one query.

    `documents` is the matched set, once. Records name a document by id rather than
    carrying its title, for the same reason the corpus does: a title repeated on eight
    rows is eight chances to disagree with itself.
    """

    intervention_class: str
    documents: tuple[CorpusDocument, ...] = ()
    attributes: tuple[AttributeGroup, ...] = ()
    built_at: str = ""

    @property
    def documents_matched(self) -> int:
        return len(self.documents)


def run_query(corpus: Corpus, query: CorpusQuery) -> CorpusAnswer:
    """Select and group. Nothing is computed that a reader could not recompute."""
    documents = _matching_documents(corpus, query)
    by_document = {document.id: document for document in documents}
    records = [record for record in corpus.records if record.document_id in by_document]

    wanted_columns = set(query.columns())
    groups: list[AttributeGroup] = []
    for column in indexed_attributes(query.intervention_class):
        if column.attribute not in wanted_columns:
            continue
        groups.append(
            AttributeGroup(
                attribute=column.attribute,
                quantity=column.quantity,
                tag_vocabulary=column.tags,
                groups=_by_source_type(
                    [record for record in records if record.attribute == column.attribute],
                    by_document,
                ),
            )
        )
    return CorpusAnswer(
        intervention_class=query.intervention_class,
        documents=documents,
        attributes=tuple(groups),
        built_at=corpus.built_at,
    )


def _matching_documents(corpus: Corpus, query: CorpusQuery) -> tuple[CorpusDocument, ...]:
    """The documents a query is about, in corpus order.

    Tag filters are applied to documents rather than to rows, and the distinction matters:
    a reader filtering for `infants` wants every column of the profiles written for
    infants, not only their target-population row.
    """
    wanted = [
        document
        for document in corpus.documents
        if document.intervention_class == query.intervention_class
        and (not query.indications or document.indication in query.indications)
        and (not query.source_types or document.source_type in query.source_types)
        and (not query.orgs or document.org in query.orgs)
    ]
    for tag_filter in query.tags:
        if not tag_filter.values:
            continue
        allowed = set(tag_filter.values)
        tagged = {
            record.document_id
            for record in corpus.records
            if record.attribute == tag_filter.attribute and allowed & set(record.tags)
        }
        wanted = [document for document in wanted if document.id in tagged]
    return tuple(wanted)


def _by_source_type(
    records: list[CorpusRecord],
    by_document: dict[str, CorpusDocument],
) -> tuple[SourceTypeGroup, ...]:
    buckets: dict[str, dict[str, list]] = {}
    for record in records:
        document = by_document[record.document_id]
        bucket = buckets.setdefault(
            document.source_type, {"values": [], "uncertain": [], "silent": []}
        )
        if record.status == "stated":
            bucket["values"].append(record)
        elif record.status == "uncertain":
            bucket["uncertain"].append(record)
        else:
            bucket["silent"].append(record.document_id)
    return tuple(
        SourceTypeGroup(
            source_type=source_type,
            values=tuple(bucket["values"]),
            uncertain=tuple(bucket["uncertain"]),
            silent=tuple(dict.fromkeys(bucket["silent"])),
        )
        # Sorted so two runs over the same corpus answer identically. Corpus order would
        # do for documents, but a source type first appears wherever its first document
        # happens to sit.
        for source_type, bucket in sorted(buckets.items())
    )


def available_filters(corpus: Corpus, intervention_class: str) -> dict[str, tuple[str, ...]]:
    """What the corpus actually contains, for building a picker.

    Named for what it is rather than borrowing Searcher's word for a similar idea. A
    `QueryFacets` there is a set of fields sent to a retrieval provider; this is a
    description of a static table. Sharing the noun would suggest the two are the same
    mechanism.

    Derived from the corpus rather than from the vocabulary: offering every declared
    indication when the archive holds three of them produces a filter that returns
    nothing and tells a reader nothing about why.
    """
    documents = [
        document
        for document in corpus.documents
        if document.intervention_class == intervention_class
    ]
    # All three sorted, on the same rule. Indications were in first-appearance order,
    # which is neither the vocabulary's order nor alphabetical - it is wherever the first
    # document holding one happened to sit, so adding a document reshuffled the picker.
    return {
        "indications": tuple(sorted({document.indication for document in documents})),
        "source_types": tuple(sorted({document.source_type for document in documents})),
        "orgs": tuple(sorted({document.org for document in documents})),
    }
