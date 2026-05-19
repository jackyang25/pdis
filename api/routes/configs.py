"""Config discovery — what (org, source_type, intervention) triples exist
and what therapeutic_areas an intervention supports.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from services.evidence import find_config as find_evidence_config

from api.schemas import TherapeuticAreasResponse, TriplesResponse

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
CHUNKER_CONFIGS_DIR = ROOT_DIR / "services" / "chunker" / "configs"


@router.get("/triples", response_model=TriplesResponse)
def list_triples() -> TriplesResponse:
    """Discover available (org, source_type, intervention) triples from chunker config filenames."""
    triples: set[tuple[str, str, str]] = set()
    for path in sorted(CHUNKER_CONFIGS_DIR.glob("*.yaml")):
        if "TEMPLATE" in path.stem.upper():
            continue
        parts = path.stem.split("_")
        if len(parts) < 3:
            continue
        triples.add((parts[0], parts[1], "_".join(parts[2:])))

    orgs = sorted({org for org, _, _ in triples})
    source_types_by_org: dict[str, list[str]] = {}
    interventions_by_org_source: dict[str, list[str]] = {}
    for org, source_type, intervention in triples:
        source_types_by_org.setdefault(org, [])
        if source_type not in source_types_by_org[org]:
            source_types_by_org[org].append(source_type)
        key = f"{org}__{source_type}"
        interventions_by_org_source.setdefault(key, [])
        if intervention not in interventions_by_org_source[key]:
            interventions_by_org_source[key].append(intervention)
    for values in source_types_by_org.values():
        values.sort()
    for values in interventions_by_org_source.values():
        values.sort()
    return TriplesResponse(
        orgs=orgs,
        source_types_by_org=source_types_by_org,
        interventions_by_org_source=interventions_by_org_source,
    )


@router.get("/therapeutic-areas", response_model=TherapeuticAreasResponse)
def list_therapeutic_areas(intervention: str) -> TherapeuticAreasResponse:
    """Read therapeutic_areas from the evidence config for the given intervention."""
    try:
        config = find_evidence_config(intervention)
        return TherapeuticAreasResponse(therapeutic_areas=list(config.therapeutic_areas))
    except LookupError:
        return TherapeuticAreasResponse(therapeutic_areas=[])
