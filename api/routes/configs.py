"""Config discovery — surfaces what the picker needs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from shared.vocabulary import indications_for

from services.scout import (
    find_config as find_scout_config,
    load_attributes as load_scout_attributes,
)
from services.chunker import available_configs as available_chunker_configs
from services.inspector import has_config as has_inspector_config
from services.inspector.configuration import find_profile, profile_catalog
from services.screener import available_configs as available_screener_configs

from api.schemas import (
    ContextOption,
    ContextsResponse,
    DocumentType,
    DocumentTypesResponse,
    IndicationsResponse,
    InspectorProfileOut,
)

router = APIRouter()

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
                    "inspector": _has_inspector_config(org, source_type, intervention),
                    "scout": _has_scout_config(org, source_type, intervention),
                },
            )
        )
    return DocumentTypesResponse(document_types=items)


@router.get("/contexts", response_model=ContextsResponse)
def list_contexts() -> ContextsResponse:
    """Context availability comes from each tool's own configuration authority."""
    contexts: dict[tuple[str, str], ContextOption] = {}
    for document in list_document_types().document_types:
        key = (document.org, document.intervention_class)
        context = contexts.setdefault(
            key, ContextOption(org=key[0], intervention_class=key[1], supports={})
        )
        for tool, supported in document.supports.items():
            context.supports[tool] = context.supports.get(tool, False) or supported

    # Screener needs a gate bank, not a document taxonomy. It must remain usable
    # when no Chunker configuration exists for the bank's product context.
    for bank in available_screener_configs():
        for intervention in sorted(bank.intervention_classes):
            key = (bank.org, intervention)
            context = contexts.setdefault(
                key, ContextOption(org=key[0], intervention_class=key[1], supports={})
            )
            context.supports["screener"] = True
    return ContextsResponse(contexts=[contexts[key] for key in sorted(contexts)])


@router.get("/indications", response_model=IndicationsResponse)
def list_indications(intervention: str) -> IndicationsResponse:
    """Expose canonical context keys through the shared vocabulary reader."""
    return IndicationsResponse(indications=indications_for(intervention))


@router.get("/inspector", response_model=InspectorProfileOut)
def get_inspector_profile(
    org: str, source_type: str, intervention_class: str
) -> InspectorProfileOut:
    try:
        profile = find_profile(org, source_type, intervention_class)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InspectorProfileOut(**profile_catalog(profile))


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
