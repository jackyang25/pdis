"""Archivist - what the Foundation's own product profiles have said before.

Public contract: consumers import from this package root only. Internals (`stages/`,
`quantity.py`, the build script's helpers) are not part of the contract.

Archivist is the one workspace tool that judges nothing. Inspector holds a document to a
rubric, Scout to external evidence, Aligner to another document, Expert to a gate's
question bank - each returns a verdict against an authority. Archivist's authority is the
corpus itself, and a corpus is data rather than judgment, so what it returns is a
selection of rows and the counts a reader could recompute from them.

That is also why the corpus is a committed artifact rather than something built on
request. Every row is a model's reading of a confidential document, and nobody should be
shown "24 months, cited to block b-0042" before a person has read that line and agreed
with it. The read path (`query`) makes no model call at all.
"""

from .corpus_store import (
    CORPUS_FILE,
    CORPUS_VERSION,
    MANIFEST_FILE,
    corpus_exists,
    load_corpus,
    write_corpus,
)
from .indexed_attributes import (
    INDEXED_ATTRIBUTES,
    MISSING_INDEXED_CLASSES,
    QUANTITY_KINDS,
    IndexedAttribute,
    filterable_attributes,
    indexed_attribute,
    indexed_attributes,
    tag_vocabulary,
)
from .manifest import ManifestEntry, load_manifest, resolve_source
from .models import (
    RECORD_STATUSES,
    VALUE_BOUNDS,
    Corpus,
    CorpusDocument,
    CorpusRecord,
    records_for,
)
from .query import (
    AttributeGroup,
    CorpusAnswer,
    CorpusQuery,
    SourceTypeGroup,
    TagFilter,
    available_filters,
    run_query,
)

__all__ = [
    "AttributeGroup",
    "CORPUS_FILE",
    "CORPUS_VERSION",
    "Corpus",
    "CorpusAnswer",
    "CorpusDocument",
    "CorpusQuery",
    "CorpusRecord",
    "INDEXED_ATTRIBUTES",
    "IndexedAttribute",
    "MANIFEST_FILE",
    "MISSING_INDEXED_CLASSES",
    "ManifestEntry",
    "QUANTITY_KINDS",
    "RECORD_STATUSES",
    "SourceTypeGroup",
    "TagFilter",
    "VALUE_BOUNDS",
    "available_filters",
    "corpus_exists",
    "filterable_attributes",
    "indexed_attribute",
    "indexed_attributes",
    "load_corpus",
    "load_manifest",
    "records_for",
    "resolve_source",
    "run_query",
    "tag_vocabulary",
    "write_corpus",
]
