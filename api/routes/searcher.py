"""Searcher route - run a query across selected backends, return Findings."""

from __future__ import annotations

import os

from fastapi import APIRouter, Form
from fastapi.responses import StreamingResponse

from services.searcher import findings_to_dicts, run_pipeline

from api.deps import get_openai_client
from api.schemas import FindingOut, SearcherRunResponse
from api.streaming import run_with_progress

router = APIRouter()

# The retrieval lanes the searcher service supports. The UI mirrors this list;
# unknown values are dropped so a typo can't silently run nothing.
VALID_BACKENDS = ("web", "pubmed", "clinicaltrials")


@router.post("/run")
async def run_searcher(
    query: str = Form(...),
    backends: str = Form("web"),
) -> StreamingResponse:
    selected = tuple(
        b.strip() for b in backends.split(",") if b.strip() in VALID_BACKENDS
    ) or ("web",)
    ncbi_api_key = os.environ.get("NCBI_API_KEY")

    def work(progress):
        llm_client = get_openai_client()
        findings = run_pipeline(
            query,
            llm_client=llm_client,
            backends=selected,
            ncbi_api_key=ncbi_api_key,
            progress_callback=progress,
        )
        return SearcherRunResponse(
            query=query,
            findings=[FindingOut(**d) for d in findings_to_dicts(findings)],
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
