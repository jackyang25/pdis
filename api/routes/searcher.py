"""Searcher routes - discover adapters and run a query across selected sources."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse

from services.searcher import ENTITY_TYPES, RetrievalEntity

from api.operations.errors import OperationError
from api.operations.searcher import (
    SearchInput,
    execute_search,
    list_sources as discover_sources,
    prepare_search,
)
from api.schemas import SearchSourceOut
from api.streaming import run_with_progress

router = APIRouter()


def _parse_entities(raw: str) -> tuple[RetrievalEntity, ...]:
    """Read `name:type` pairs, refusing an unknown type rather than dropping it.

    A dropped entity is the failure this whole field exists to end: the run would
    proceed, the source needing that entity would report a skip, and nothing would say
    the caller had named it. So a bad type is a 422 with the accepted list.
    """
    stated: list[RetrievalEntity] = []
    for part in (piece.strip() for piece in raw.split(",")):
        if not part:
            continue
        name, _, entity_type = part.rpartition(":")
        name, entity_type = name.strip(), entity_type.strip().lower()
        if not name or entity_type not in ENTITY_TYPES:
            raise ValueError(
                f"{part!r} is not a `name:type` pair. Accepted types: "
                f"{', '.join(sorted(ENTITY_TYPES))}"
            )
        stated.append(RetrievalEntity(name=name, entity_type=entity_type))
    return tuple(stated)


@router.get("/sources", response_model=list[SearchSourceOut])
def list_sources() -> list[SearchSourceOut]:
    """Expose registered source metadata so clients do not mirror an allowlist."""
    try:
        return discover_sources()
    except OperationError as exc:
        raise HTTPException(status_code=500, detail=exc.message) from exc


@router.post("/run")
async def run_searcher(
    query: str = Form(...),
    sources: str = Form(""),
    # Forwarded, not dropped. These are `run_pipeline` parameters, so leaving them
    # unwired made the interface narrower than the function it calls: a field-addressed
    # source fell back to anchoring on `query` itself and returned nothing.
    condition: str = Form(""),
    intervention: str = Form(""),
    # The fourth slot of the one request. Sent as `name:type` pairs so a caller states
    # the type rather than the server guessing it: `BRAF` is a gene here and a protein
    # there, and which one decides whether Open Targets or ChEMBL can address it.
    entities: str = Form(""),
    # One named product, narrowing the request the intervention class scopes. Distinct
    # from `intervention`, which is the class: a source issues both requests.
    product: str = Form(""),
    # The remaining two subject facets. Read by the literature grammars to pick the one
    # phrase a query asks about; the structured sources have no such field.
    population: str = Form(""),
    outcome: str = Form(""),
    # The window, stated to the provider rather than applied to its answer. Only lanes
    # declaring `honors_date_bound` can act on it; the rest ignore it.
    # Scopes the run, not one query, so a source with a location field can restrict on
    # it rather than matching the place name as text.
    region: str = Form(""),
    published_since: str = Form(""),
) -> StreamingResponse:
    try:
        prepared = prepare_search(
            SearchInput(
                query=query,
                sources=[
                    source.strip() for source in sources.split(",") if source.strip()
                ],
                condition=condition,
                intervention=intervention,
                entities=[
                    {"name": entity.name, "entity_type": entity.entity_type}
                    for entity in _parse_entities(entities)
                ],
                product=product,
                population=population,
                outcome=outcome,
                region=region,
                published_since=published_since,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OperationError as exc:
        status = 500 if exc.code == "missing_configuration" else 422
        raise HTTPException(status_code=status, detail=exc.message) from exc

    def work(progress):
        return execute_search(prepared, progress).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
