"""Run one case through its tool, composed as that tool's API route composes it.

Clients come from `api.deps`, document identities from `api.uploads`, and each result
is published through the route's own response schema, so the saved file is what the
browser would receive. Only the transport is missing: no HTTP, no temporary upload. Each runner imports its
tool on first use, so `--only` runs a tool while another is mid-edit.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from api.deps import get_openai_client, get_quantitative_anthropic_client, get_search_runtime
from api.uploads import document_upload_parts, require_distinct_doc_ids
from services.chunker import DOCUMENT_SUFFIXES

from .measure import Case

Progress = Callable[..., object]


def run_case(case: Case, root: Path, progress: Progress) -> dict:
    return _RUNNERS[case.tool](case, root, progress)


def _documents(case: Case, root: Path, tool: str, suffixes=DOCUMENT_SUFFIXES) -> list[tuple[str, str, str]]:
    """(document type, absolute path, doc_id) per document, doc_id derived as uploads derive it."""
    documents = []
    for role, relative in case.documents:
        path = Path(root) / relative
        doc_id, _ = document_upload_parts(path.name, tool=tool, accepted_suffixes=suffixes)
        documents.append((role, str(path), doc_id))
    require_distinct_doc_ids([doc_id for _, _, doc_id in documents])
    return documents


def _inspector(case: Case, root: Path, progress: Progress) -> dict:
    from api.operations.inspector import execute_inspection, prepare_inspection

    prepared = prepare_inspection(
        org=case.org, source_type=case.source_type, intervention_class=case.intervention_class,
        applicability_facts=case.applicability_facts,
    )
    ((_, path, doc_id),) = _documents(case, root, "Inspector")
    return execute_inspection(
        path, prepared=prepared, indication=case.indication, llm_client=get_openai_client(),
        progress_callback=progress, doc_id=doc_id,
    )


def _aligner(case: Case, root: Path, progress: Progress) -> dict:
    from api.schemas import AlignerRunResponse, AlignmentResultOut
    from services.aligner import DocumentInput, load_config, run_pipeline

    documents = [DocumentInput(file_path=path, source_type=role, doc_id=doc_id)
                 for role, path, doc_id in _documents(case, root, "Aligner")]
    result = run_pipeline(
        documents, org=case.org, intervention_class=case.intervention_class,
        indication=case.indication, config=load_config(), llm_client=get_openai_client(),
        progress_callback=progress,
    )
    return AlignerRunResponse(alignment=AlignmentResultOut(**asdict(result))).model_dump()


def _screener(case: Case, root: Path, progress: Progress) -> dict:
    from api.schemas import GateReviewOut, ScreenerRunResponse
    from services.screener import (
        SUPPORTED_DOCUMENT_SUFFIXES, DocumentInput, find_config, resolve_questions, run_pipeline,
    )

    config = find_config(case.org, case.gate)
    resolve_questions(config, intervention_class=case.intervention_class)
    documents = [DocumentInput(file_path=path, doc_id=doc_id)
                 for _, path, doc_id in _documents(case, root, "Screener", SUPPORTED_DOCUMENT_SUFFIXES)]
    result = run_pipeline(
        documents, org=case.org, intervention_class=case.intervention_class,
        indication=case.indication, config=config, llm_client=get_openai_client(),
        progress_callback=progress,
    )
    return ScreenerRunResponse(review=GateReviewOut(**asdict(result))).model_dump()


def _drafter(case: Case, root: Path, progress: Progress) -> dict:
    from api.schemas import DrafterRunResponse, DraftResultOut
    from services.drafter import run_pipeline

    llm_client = get_openai_client()
    result = run_pipeline(
        org=case.org, intervention_class=case.intervention_class, indication=case.indication,
        llm_client=llm_client, runtime=get_search_runtime(llm_client), progress_callback=progress,
    )
    return DrafterRunResponse(result=DraftResultOut(**result.to_dict())).model_dump()


def _scout(case: Case, root: Path, progress: Progress) -> dict:
    """Draft, settle the target review as below, then continue.

    The result is the continuation's as the server publishes it. When prose
    measurements await admission that is the `evidence_review` checkpoint: admission
    and the statistics recomputed from it happen in the browser, so they are not
    evaluated here.
    """
    from api.routes.scout import _response_from_result
    from api.schemas import ScoutContinueRequest
    from services.scout import continue_pipeline, find_config, result_from_target_review, run_pipeline

    header = dict(org=case.org, source_type=case.source_type,
                  intervention_class=case.intervention_class, indication=case.indication)
    config = find_config(case.org, case.source_type, case.intervention_class)
    openai_client = get_openai_client()
    clients = dict(openai_client=openai_client,
                   quantitative_mapping_client=get_quantitative_anthropic_client(),
                   retrieval_runtime=get_search_runtime(openai_client))
    documents = _documents(case, root, "Scout")
    draft = run_pipeline(
        [path for _, path, _ in documents], doc_ids=[doc_id for _, _, doc_id in documents],
        config=config, published_since=case.published_since, progress_callback=progress,
        **clients, **header,
    )
    reviewed = settle_target_review(_response_from_result(draft, **header).model_dump())
    # Validated through the continuation request, as the `/continue` route receives it.
    request = ScoutContinueRequest(draft=reviewed)
    final = continue_pipeline(
        result_from_target_review(request.draft.model_dump()), config=config,
        progress_callback=progress, **clients, **header,
    )
    return _response_from_result(final, **header).model_dump()


def settle_target_review(draft: dict) -> dict:
    """The harness's fixed reviewer, so every run continues from the same policy.

    Targets awaiting review take the AI recommendation where it is decisive -
    `confirm` approves, `exclude` rejects, as the page's "accept recommendations"
    does - and the undecided `flag` and `unavailable` are approved, keeping in the
    run every target the AI did not exclude. Statements awaiting review accept
    their exclusion, the one decision the page offers for them.
    """
    ledger = draft["quantitative_ledger"]
    for target in ledger["targets"]:
        if target["review_status"] == "needs_review":
            target["review_status"] = "rejected" if target["ai_recommendation"] == "exclude" else "approved"
    for review in ledger["reviews"]:
        if review["review_status"] == "needs_review":
            review["review_status"] = "accepted_exclusion"
    return draft


_RUNNERS = {
    "inspector": _inspector, "aligner": _aligner, "screener": _screener,
    "scout": _scout, "drafter": _drafter,
}
