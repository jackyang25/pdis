"""Transport-neutral Inspector application operation."""

from __future__ import annotations

from dataclasses import dataclass

from services.inspector import (
    find_profile,
    InspectionProfile,
    inspection_result_to_dict,
    run_profile_pipeline,
    validate_product_facts,
)
from api.schemas import InspectionResultOut, InspectorRunResponse


@dataclass(frozen=True)
class PreparedInspection:
    profile: InspectionProfile
    applicability_facts: dict[str, str]


def prepare_inspection(
    *, org: str, source_type: str, intervention_class: str,
    applicability_facts: dict[str, str],
) -> PreparedInspection:
    return PreparedInspection(
        profile=find_profile(org, source_type, intervention_class),
        applicability_facts=validate_product_facts(applicability_facts),
    )


def execute_inspection(
    file_path: str, *, prepared: PreparedInspection,
    indication: str, llm_client,
    max_tokens: int, progress_callback=None, doc_id: str | None = None,
    pipeline=run_profile_pipeline,
) -> dict:
    result = pipeline(
        file_path, profile=prepared.profile,
        applicability_facts=prepared.applicability_facts,
        llm_client=llm_client, indication=indication, max_tokens=max_tokens,
        progress_callback=progress_callback, doc_id=doc_id,
    )
    response = InspectorRunResponse(
        inspection=InspectionResultOut(**inspection_result_to_dict(result))
    )
    return response.model_dump()
