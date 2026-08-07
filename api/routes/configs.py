"""Config discovery — surfaces what the picker needs."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from services.scout import (
    find_config as find_scout_config,
    load_attributes as load_scout_attributes,
)
from services.chunker import available_configs as available_chunker_configs
from services.inspector import has_config as has_inspector_config

from api.schemas import (
    DocumentType,
    DocumentTypesResponse,
    IndicationsResponse,
)

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
INDICATIONS_VOCAB = ROOT_DIR / "shared" / "indications.yaml"


@router.get("/document-types", response_model=DocumentTypesResponse)
def list_document_types() -> DocumentTypesResponse:
    items: list[DocumentType] = []
    for config in available_chunker_configs():
        org = config.org
        source_type = config.source_type
        intervention = config.intervention_class
        items.append(
            DocumentType(
                key=config.type_key,
                org=org,
                source_type=source_type,
                intervention_class=intervention,
                display_name=config.display_name or config.type_key,
                supports={
                    "chunker": True,
                    # Aligner uses the Chunker contract for both documents and
                    # owns one source-type-neutral alignment configuration.
                    "aligner": True,
                    # Expert reads every document type. Its question banks are keyed
                    # by gate and place no restriction on which documents a run may
                    # supply, so a parseable type is a usable one.
                    "expert": True,
                    "inspector": _has_inspector_config(org, source_type, intervention),
                    "scout": _has_scout_config(org, source_type, intervention),
                },
            )
        )
    return DocumentTypesResponse(document_types=items)


@router.get("/indications", response_model=IndicationsResponse)
def list_indications(intervention: str) -> IndicationsResponse:
    """Return indications for an intervention from the shared vocabulary file."""
    if not INDICATIONS_VOCAB.exists():
        return IndicationsResponse(indications=[])
    with INDICATIONS_VOCAB.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return IndicationsResponse(indications=list(data.get(intervention, []) or []))


def _has_inspector_config(org: str, source_type: str, intervention: str) -> bool:
    return has_inspector_config(org, source_type, intervention)



def _has_scout_config(org: str, source_type: str, intervention: str) -> bool:
    """Scout is usable when a config exists and the config can produce units.

    A 'vocabulary' config needs non-empty shared attributes (an empty list would
    produce an empty grid). An 'extract' config pulls units from the document
    itself, so it does not depend on the shared vocabulary.
    """
    try:
        config = find_scout_config(org, source_type, intervention)
    except LookupError:
        return False
    if config.unit_provider == "extract":
        return True
    return bool(load_scout_attributes(intervention))
