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

from evidence.models import Claim, load_config  # noqa: E402
from evidence.pipeline import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    EXTRACTORS,
    default_source_id_from_path,
    run_pipeline,
)
from llm_client import create_llm_client, default_model_for_provider  # noqa: E402
from tools._widgets import render_advanced_controls, render_llm_controls  # noqa: E402


SUPPORTED_UPLOAD_TYPES = ["docx", "pdf"]


def main() -> None:
    st.set_page_config(page_title="Evidence — Claim Pipeline", layout="wide")
    render()


def render() -> None:
    """Stateless evidence pipeline UI.

    Mirrors chunker's pattern: upload one document, run the pipeline,
    show the output, offer a download. No persistence.
    """
    st.title("Evidence — Claim Pipeline")
    st.caption(
        "Upload a document, run the parse → extract → bind → appraise pipeline, "
        "and inspect the resulting claims. Stateless: download or save the output yourself."
    )

    config_entries = _discover_configs()
    if not config_entries:
        st.error(
            "No AttributeConfig files found in evidence/configs/. "
            "Copy CONFIG_TEMPLATE.yaml and fill in real attributes."
        )
        st.stop()

    config_display = st.sidebar.selectbox(
        "AttributeConfig",
        [display for display, _ in config_entries],
        help="Defines the attribute namespace claims are bound to.",
    )
    config_file = next(file for display, file in config_entries if display == config_display)
    config = load_config(_config_path(config_file))

    source_type = st.sidebar.selectbox(
        "Source type",
        sorted(EXTRACTORS.keys()),
        help="Which extractor to use. Only `product_profile` is wired today.",
    )

    intervention_class = st.sidebar.selectbox(
        "Intervention class (optional)",
        [""] + list(config.intervention_classes),
    ) or None
    therapeutic_area = st.sidebar.selectbox(
        "Therapeutic area (optional)",
        [""] + list(config.therapeutic_areas),
    ) or None

    uploaded_file = st.sidebar.file_uploader(
        "Upload document (.docx or .pdf)",
        type=SUPPORTED_UPLOAD_TYPES,
    )

    provider, model, api_key = render_llm_controls(
        "evidence",
        default_model_for_provider=default_model_for_provider,
        env_fallback=False,
    )
    advanced = render_advanced_controls(
        "evidence",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"**Config**: `{config.type_key}`  \n"
        f"**Attributes**: {len(config.attributes)}  \n"
        f"**Source type**: `{source_type}`"
    )

    if uploaded_file is None:
        st.info("Step 1: upload a document to begin.")
        return

    source_id = st.text_input(
        "Source ID",
        value=default_source_id_from_path(uploaded_file.name),
        help="Stable identifier for this document. Example: who_ppc_malaria_vaccine_2022",
    )

    run_pipeline_button = st.button("Run Pipeline", type="primary")
    if not run_pipeline_button:
        st.info(
            "Step 2: choose config + source type + identifiers in the sidebar, "
            "then click Run Pipeline. The pipeline parses the document, extracts "
            "draft claims, binds them to attributes via an LLM, and appraises "
            "reliability."
        )
        return

    if not api_key:
        st.error(f"Enter a {provider.title()} API key in the sidebar to run the pipeline.")
        return

    file_bytes = uploaded_file.getvalue()
    file_suffix = Path(uploaded_file.name).suffix.lower() or ".docx"

    with st.spinner("Running pipeline (parse → extract → bind → appraise)..."):
        try:
            blocks, claims = _run_pipeline_on_upload(
                file_bytes=file_bytes,
                file_suffix=file_suffix,
                doc_id=source_id,
                source_type=source_type,
                source_id=source_id,
                config=config,
                intervention_class=intervention_class,
                therapeutic_area=therapeutic_area,
                provider=provider,
                model=model,
                api_key=api_key,
                max_tokens=advanced["max_tokens"],
            )
        except Exception as exc:
            st.error(f"Pipeline failed: {exc}")
            return

    st.success(
        f"Pipeline completed. Parsed {len(blocks)} blocks; produced {len(claims)} claims."
    )
    _render_summary(claims)
    _render_claim_list(claims)
    _render_download(claims, source_id)


# ---------------------------------------------------------------------------
# Pipeline driver
# ---------------------------------------------------------------------------


def _run_pipeline_on_upload(
    *,
    file_bytes: bytes,
    file_suffix: str,
    doc_id: str,
    source_type: str,
    source_id: str,
    config,
    intervention_class: str | None,
    therapeutic_area: str | None,
    provider: str,
    model: str,
    api_key: str,
    max_tokens: int,
):
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        llm_client = create_llm_client(provider, api_key, model)
        return run_pipeline(
            file_path=temp_path,
            doc_id=doc_id,
            source_type=source_type,
            source_id=source_id,
            config=config,
            llm_client=llm_client,
            intervention_class=intervention_class,
            therapeutic_area=therapeutic_area,
            max_tokens=max_tokens,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


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


def _config_path(file_name: str) -> str:
    return str(ROOT_DIR / "evidence" / "configs" / file_name)


def _discover_configs() -> list[tuple[str, str]]:
    configs_dir = ROOT_DIR / "evidence" / "configs"
    entries: list[tuple[str, str]] = []
    for path in sorted(configs_dir.glob("*.yaml")):
        try:
            config = load_config(str(path))
        except Exception:
            continue
        entries.append((config.display_name, path.name))
    return entries


if __name__ == "__main__":
    main()
