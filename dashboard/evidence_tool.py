from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

from services.evidence import BatchResult, Claim  # noqa: E402
from services.evidence import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    EXTRACTORS,
    default_source_id_from_path,
    run_pipeline,
    run_pipeline_batch,
)
from llm_client import create_llm_client, default_model_for_provider  # noqa: E402
from dashboard._ui import (  # noqa: E402
    render_advanced_controls,
    render_empty_state,
    render_header,
    render_llm_controls,
    render_section,
)



SUPPORTED_UPLOAD_TYPES = ["docx", "pdf"]


def main() -> None:
    st.set_page_config(page_title="Evidence — Claim Pipeline", layout="wide")
    render()


def render(header=None, config=None) -> None:
    """Render the evidence UI. `header` and `config` come from app.py."""
    render_header(
        "Evidence",
        "Claim Pipeline",
        caption="Parse a document, then extract → bind → appraise to produce "
        "source-backed claims grounded in an AttributeConfig.",
    )

    if config is None or header is None:
        render_empty_state("Pick a document type in the sidebar.")
        return

    if "evidence_upload_counter" not in st.session_state:
        st.session_state["evidence_upload_counter"] = 0
    if "evidence_batch_upload_counter" not in st.session_state:
        st.session_state["evidence_batch_upload_counter"] = 0

    render_section("mode (ui)")
    mode = st.sidebar.selectbox(
        "mode",
        ["single", "batch"],
        key="evidence_mode",
        label_visibility="collapsed",
    )
    if mode == "batch":
        _render_batch_mode(header=header, config=config)
        return

    _render_single_mode(header=header, config=config)


def _render_single_mode(*, header, config) -> None:
    render_section("input")
    uploaded_file = st.sidebar.file_uploader(
        "input_dir (one .docx or .pdf)",
        type=SUPPORTED_UPLOAD_TYPES,
        key=f"evidence_upload_{st.session_state['evidence_upload_counter']}",
    )
    source_kind = _select_source_kind(key="evidence_single_source_kind")

    provider, model, api_key = render_llm_controls(
        "evidence_single",
        default_model_for_provider=default_model_for_provider,
        env_fallback=False,
    )
    advanced = render_advanced_controls(
        "evidence_single",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    )

    if st.sidebar.button("run"):
        if uploaded_file is None:
            st.error("Upload a document before running the pipeline.")
        elif not api_key:
            st.error(f"Enter a {provider.title()} API key before running the pipeline.")
        else:
            _run_single_pipeline(
                uploaded_file=uploaded_file,
                config=config,
                header=header,
                source_kind=source_kind,
                provider=provider,
                model=model,
                api_key=api_key,
                max_tokens=advanced["max_tokens"],
            )

    if st.sidebar.button("clear / restart"):
        _restart_session()

    result = st.session_state.get("evidence_single_result")
    if result is None:
        render_empty_state("Upload a `.docx` or `.pdf` document to begin.")
        return

    claims = result["claims"]
    source_id = result["source_id"]
    st.success(
        f"Pipeline completed. Parsed {result['block_count']} blocks; "
        f"produced {len(claims)} claims."
    )
    _render_summary(claims)
    _render_claim_list(claims)
    _render_download(claims, source_id)


def _render_batch_mode(*, header, config) -> None:
    render_section("input")
    uploaded_files = st.sidebar.file_uploader(
        "input_dir (.docx, .pdf)",
        type=SUPPORTED_UPLOAD_TYPES,
        accept_multiple_files=True,
        key=f"evidence_batch_upload_{st.session_state['evidence_batch_upload_counter']}",
    )
    source_kind = _select_source_kind(key="evidence_batch_source_kind")

    provider, model, api_key = render_llm_controls(
        "evidence_batch",
        default_model_for_provider=default_model_for_provider,
        env_fallback=False,
    )
    advanced = render_advanced_controls(
        "evidence_batch",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        show_max_workers=True,
    )

    if st.sidebar.button("run"):
        if not uploaded_files:
            st.error("Upload one or more documents before running.")
        elif not api_key:
            st.error(f"Enter a {provider.title()} API key before running.")
        else:
            _run_batch_pipeline(
                uploaded_files=uploaded_files,
                config=config,
                header=header,
                source_kind=source_kind,
                provider=provider,
                model=model,
                api_key=api_key,
                max_tokens=advanced["max_tokens"],
                max_workers=advanced["max_workers"],
            )

    if st.sidebar.button("clear / restart", key="evidence_batch_clear"):
        _restart_session()

    batch_results = st.session_state.get("evidence_batch_results")
    if not batch_results:
        render_empty_state("Upload one or more `.docx` or `.pdf` documents to begin.")
        return

    _render_batch_results(batch_results)


# ---------------------------------------------------------------------------
# Pipeline drivers
# ---------------------------------------------------------------------------


def _run_single_pipeline(
    *,
    uploaded_file,
    config,
    header,
    source_kind: str,
    provider: str,
    model: str,
    api_key: str,
    max_tokens: int,
) -> None:
    source_id = default_source_id_from_path(uploaded_file.name)
    file_suffix = Path(uploaded_file.name).suffix.lower() or ".docx"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
            temp_file.write(uploaded_file.getvalue())
            temp_path = temp_file.name
        with st.spinner("Running pipeline (parse → extract → bind → appraise)..."):
            llm_client = create_llm_client(provider, api_key, model)
            blocks, claims = run_pipeline(
                file_path=temp_path,
                doc_id=source_id,
                source_id=source_id,
                config=config,
                llm_client=llm_client,
                org=header["org"],
                source_type=header["source_type"],
                therapeutic_area=header.get("therapeutic_area"),
                source_kind=source_kind,
                max_tokens=max_tokens,
            )
        st.session_state["evidence_single_result"] = {
            "source_id": source_id,
            "block_count": len(blocks),
            "claims": claims,
        }
    except Exception as exc:
        st.session_state.pop("evidence_single_result", None)
        st.error(f"Pipeline failed: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _run_batch_pipeline(
    *,
    uploaded_files,
    config,
    header,
    source_kind: str,
    provider: str,
    model: str,
    api_key: str,
    max_tokens: int,
    max_workers: int,
) -> None:
    staged = [_stage_upload(file) for file in uploaded_files]
    try:
        jobs = [(stage["file_path"], stage["source_id"]) for stage in staged]
        with st.spinner(f"Running pipeline on {len(jobs)} documents..."):
            results = run_pipeline_batch(
                jobs,
                config=config,
                llm_client_factory=lambda: create_llm_client(provider, api_key, model),
                org=header["org"],
                source_type=header["source_type"],
                therapeutic_area=header.get("therapeutic_area"),
                source_kind=source_kind,
                max_tokens=max_tokens,
                max_workers=max_workers,
            )
        st.session_state["evidence_batch_results"] = results
    finally:
        for stage in staged:
            if os.path.exists(stage["file_path"]):
                os.unlink(stage["file_path"])


def _stage_upload(uploaded_file) -> dict:
    source_id = default_source_id_from_path(uploaded_file.name)
    file_suffix = Path(uploaded_file.name).suffix.lower() or ".docx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        return {"file_path": temp_file.name, "source_id": source_id}


def _restart_session() -> None:
    st.session_state.pop("evidence_single_result", None)
    st.session_state.pop("evidence_batch_results", None)
    st.session_state["evidence_upload_counter"] += 1
    st.session_state["evidence_batch_upload_counter"] += 1
    st.rerun()


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_batch_results(batch_results: list[BatchResult]) -> None:
    succeeded = [r for r in batch_results if r.error is None]
    failed = [r for r in batch_results if r.error is not None]
    total_claims = sum(len(r.claims) for r in succeeded)
    st.success(
        f"Pipeline completed on {len(succeeded)} of {len(batch_results)} documents; "
        f"produced {total_claims} claims."
    )

    if failed:
        with st.expander(f"Failures ({len(failed)})"):
            for result in failed:
                st.error(f"{result.source_id}: {result.error}")

    st.subheader("Batch Overview")
    st.dataframe(
        [
            {
                "source": r.source_id,
                "blocks": len(r.blocks),
                "claims": len(r.claims),
                "status": "ok" if r.error is None else "error",
            }
            for r in batch_results
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Per-Document Claims")
    for result in batch_results:
        if result.error is not None:
            continue
        with st.expander(f"{result.source_id} — {len(result.claims)} claims"):
            _render_summary(result.claims)
            _render_claim_list(result.claims)

    st.subheader("Downloads")
    all_claims = [c for r in succeeded for c in r.claims]
    cols = st.columns(2)
    cols[0].download_button(
        "claims.jsonl",
        data=_claims_to_jsonl(all_claims),
        file_name="claims.jsonl",
        mime="application/jsonl",
    )
    cols[1].download_button(
        "claims.csv",
        data=_claims_to_csv(all_claims),
        file_name="claims.csv",
        mime="text/csv",
    )


def _render_summary(claims: list[Claim]) -> None:
    st.subheader("Pipeline Output Summary")
    if not claims:
        st.info("No claims produced. Check that the document contains PPC/TPP-style tables.")
        return

    type_counts = Counter(c.claim_type for c in claims)
    strength_counts = Counter(c.evidence_strength for c in claims if c.evidence_strength)
    binding_counts = Counter(c.binding_confidence for c in claims if c.binding_confidence)
    unbound = sum(1 for c in claims if not c.attribute_ref)

    cols = st.columns(4)
    cols[0].metric("Total claims", len(claims))
    cols[1].metric("Bound (with attribute_ref)", len(claims) - unbound)
    cols[2].metric("Unbound", unbound)
    cols[3].metric("Strong evidence", strength_counts.get("strong", 0))

    with st.expander("Counts by claim_type"):
        st.dataframe(
            [{"claim_type": k, "count": v} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])],
            width="stretch",
            hide_index=True,
        )
    with st.expander("Counts by binding_confidence"):
        st.dataframe(
            [{"binding_confidence": k, "count": v} for k, v in sorted(binding_counts.items(), key=lambda x: -x[1])],
            width="stretch",
            hide_index=True,
        )


def _render_claim_list(claims: list[Claim]) -> None:
    if not claims:
        return
    st.subheader("Claims")
    rows = []
    for claim in claims:
        rows.append(
            {
                "id": claim.id,
                "attribute_ref": claim.attribute_ref or "—",
                "binding_confidence": claim.binding_confidence or "—",
                "claim_type": claim.claim_type,
                "evidence_strength": claim.evidence_strength or "—",
                "recency_tier": claim.recency_tier or "—",
                "statement": (claim.statement or "")[:120],
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

    with st.expander("Per-claim detail"):
        for claim in claims:
            title = (
                f"{claim.id}  |  {claim.attribute_ref or 'unbound'}  |  "
                f"{(claim.statement or '')[:80]}"
            )
            with st.expander(title):
                st.json(asdict(claim))


def _render_download(claims: list[Claim], source_id: str) -> None:
    st.subheader("Download")
    cols = st.columns(2)
    cols[0].download_button(
        label="Download Claims JSONL",
        data=_claims_to_jsonl(claims),
        file_name=f"{source_id}_claims.jsonl",
        mime="application/jsonl",
    )
    cols[1].download_button(
        label="Download Claims CSV",
        data=_claims_to_csv(claims),
        file_name=f"{source_id}_claims.csv",
        mime="text/csv",
    )


def _claims_to_jsonl(claims: list[Claim]) -> str:
    return "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in claims)


def _claims_to_csv(claims: list[Claim]) -> str:
    if not claims:
        return ""
    rows = []
    for c in claims:
        d = asdict(c)
        d["source_locator_json"] = json.dumps(d.pop("source_locator"), ensure_ascii=False)
        rows.append(d)
    fieldnames = list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _select_source_kind(*, key: str) -> str:
    """Render the source_kind picker only when more than one extractor is wired."""
    kinds = sorted(EXTRACTORS.keys())
    if len(kinds) == 1:
        return kinds[0]
    return st.sidebar.selectbox(
        "source_kind",
        kinds,
        help="CLI: --source-kind",
        key=key,
    )


if __name__ == "__main__":
    main()
