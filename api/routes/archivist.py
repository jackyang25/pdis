"""Archivist routes - read the corpus. No upload, no run, no model call.

Every other tool's route takes a document and starts work. This one takes a filter and
reads a committed artifact, which is why there is no streaming progress here and no
`Form` upload: the work happened when the corpus was built, and a reader is looking at
something a person already reviewed.

The corpus is loaded per request rather than held in a module-level cache. It is a few
hundred rows, loading re-runs every invariant, and a cache would mean a reviewer editing
the artifact has to restart the server to see it. The one place a cache would help is the
one place it would hurt.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from services.archivist import (
    INDEXED_ATTRIBUTES,
    CorpusQuery,
    TagFilter,
    available_filters,
    indexed_attributes,
    load_corpus,
    run_query,
)

from api.schemas import (
    ArchivistAttributeGroupOut,
    ArchivistColumnOut,
    ArchivistCorpusResponse,
    ArchivistDocumentOut,
    ArchivistQueryRequest,
    ArchivistQueryResponse,
    ArchivistRecordOut,
    ArchivistSourceTypeGroupOut,
)

router = APIRouter()

#: Which class a client sees first when it names none. Declared here rather than defaulted
#: to "the first key", which would change silently the day another class is indexed.
DEFAULT_INTERVENTION_CLASS = "vaccine"


def _declared_classes() -> list[str]:
    return sorted(INDEXED_ATTRIBUTES)


def _columns(intervention_class: str) -> list[ArchivistColumnOut]:
    return [
        ArchivistColumnOut(
            attribute=column.attribute,
            tags=list(column.tags),
            quantity=column.quantity,
            not_confused_with=list(column.not_confused_with),
        )
        for column in indexed_attributes(intervention_class)
    ]


def _document(document) -> ArchivistDocumentOut:
    return ArchivistDocumentOut(**asdict(document))


def _record(record) -> ArchivistRecordOut:
    data = asdict(record)
    data["tags"] = list(record.tags)
    return ArchivistRecordOut(**data)


@router.get("/corpus", response_model=ArchivistCorpusResponse)
def read_corpus(intervention_class: str = DEFAULT_INTERVENTION_CLASS) -> ArchivistCorpusResponse:
    """What the archive holds, so a client can build a query it can answer."""
    if intervention_class not in INDEXED_ATTRIBUTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No corpus columns are declared for {intervention_class!r}. "
                f"Declared: {', '.join(_declared_classes())}"
            ),
        )
    corpus = load_corpus()
    filters = available_filters(corpus, intervention_class)
    return ArchivistCorpusResponse(
        built_at=corpus.built_at,
        documents=[
            _document(document)
            for document in corpus.documents
            if document.intervention_class == intervention_class
        ],
        columns=_columns(intervention_class),
        intervention_class=intervention_class,
        intervention_classes=_declared_classes(),
        indications=list(filters["indications"]),
        source_types=list(filters["source_types"]),
        orgs=list(filters["orgs"]),
    )


@router.post("/query", response_model=ArchivistQueryResponse)
def query_corpus(request: ArchivistQueryRequest) -> ArchivistQueryResponse:
    """Read the rows a filter selects, grouped by column and then by document type."""
    try:
        query = CorpusQuery(
            intervention_class=request.intervention_class,
            attributes=tuple(request.attributes),
            indications=tuple(request.indications),
            source_types=tuple(request.source_types),
            orgs=tuple(request.orgs),
            tags=tuple(
                TagFilter(attribute=item.attribute, values=tuple(item.values))
                for item in request.tags
            ),
        )
    except (ValueError, LookupError) as exc:
        # A filter naming an undeclared column or tag is refused with the reason rather
        # than silently returning nothing, which is indistinguishable from an empty
        # archive.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    answer = run_query(load_corpus(), query)
    return ArchivistQueryResponse(
        intervention_class=answer.intervention_class,
        built_at=answer.built_at,
        documents=[_document(document) for document in answer.documents],
        attributes=[
            ArchivistAttributeGroupOut(
                attribute=group.attribute,
                quantity=group.quantity,
                tag_vocabulary=list(group.tag_vocabulary),
                groups=[
                    ArchivistSourceTypeGroupOut(
                        source_type=source_group.source_type,
                        values=[_record(record) for record in source_group.values],
                        uncertain=[_record(record) for record in source_group.uncertain],
                        silent=list(source_group.silent),
                    )
                    for source_group in group.groups
                ],
            )
            for group in answer.attributes
        ],
    )
