"""Config discovery — surfaces what the picker needs."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from services.benchmarker import find_config as find_benchmarker_config
from services.reviewer import find_config as find_reviewer_config

from api.schemas import (
    DocumentType,
    DocumentTypesResponse,
    IndicationsResponse,
)

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
CHUNKER_CONFIGS_DIR = ROOT_DIR / "services" / "chunker" / "configs"
INDICATIONS_VOCAB = ROOT_DIR / "shared" / "indications.yaml"


@router.get("/document-types", response_model=DocumentTypesResponse)
def list_document_types() -> DocumentTypesResponse:
    items: list[DocumentType] = []
    for path in sorted(CHUNKER_CONFIGS_DIR.glob("*.yaml")):
        if "TEMPLATE" in path.stem.upper():
            continue
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        try:
            org = data["org"]
            source_type = data["source_type"]
            intervention = data["intervention_class"]
        except KeyError:
            continue
        items.append(
            DocumentType(
                key=path.stem,
                org=org,
                source_type=source_type,
                intervention_class=intervention,
                display_name=data.get("display_name", path.stem),
                supports={
                    "chunker": True,
                    "benchmarker": _has_benchmarker_config(intervention),
                    "reviewer": _has_reviewer_config(org, source_type, intervention),
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


def _has_benchmarker_config(intervention: str) -> bool:
    try:
        find_benchmarker_config(intervention)
        return True
    except LookupError:
        return False


def _has_reviewer_config(org: str, source_type: str, intervention: str) -> bool:
    return find_reviewer_config(org, source_type, intervention) is not None
