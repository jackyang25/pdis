"""Searcher route - run a web search query, stream progress, return Findings."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import StreamingResponse

from services.searcher import findings_to_dicts, run_pipeline

from api.deps import get_openai_client
from api.schemas import FindingOut, SearcherRunResponse
from api.streaming import run_with_progress

router = APIRouter()


@router.post("/run")
async def run_searcher(query: str = Form(...)) -> StreamingResponse:
    def work(progress):
        llm_client = get_openai_client()
        findings = run_pipeline(
            query,
            llm_client=llm_client,
            progress_callback=progress,
        )
        return SearcherRunResponse(
            query=query,
            findings=[FindingOut(**d) for d in findings_to_dicts(findings)],
        ).model_dump()

    return StreamingResponse(run_with_progress(work), media_type="application/x-ndjson")
