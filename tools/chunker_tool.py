from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

from chunker.models import ContentBlock, blocks_to_dicts  # noqa: E402
from chunker.pipeline import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    map_blocks_batch,
    run_pipeline,
    run_pipeline_batch,
)
from llm_client import create_llm_client, default_model_for_provider  # noqa: E402
from tools._ui import (  # noqa: E402
    render_advanced_controls,
    render_empty_state,
    render_header,
    render_llm_controls,
    render_section,
)



def main() -> None:
    st.set_page_config(page_title="Chunker - Block Inspector", layout="wide")
    render()


def render(header=None, config=None) -> None:
    """Render the chunker UI. `header` and `config` come from app.py."""
    render_header(
        "Chunker",
        "Block Inspector",
        caption="Parse `.docx` and `.pdf` documents into ordered ContentBlocks, "
        "optionally label each block with a section taxonomy.",
    )

    if config is None or header is None:
        render_empty_state("Pick a document type in the sidebar.")
        return

    if "upload_counter" not in st.session_state:
        st.session_state["upload_counter"] = 0
    if "batch_upload_counter" not in st.session_state:
        st.session_state["batch_upload_counter"] = 0

    render_section("mode (ui)")
    mode = st.sidebar.selectbox(
        "mode",
        ["single", "batch"],
        key="chunker_mode",
        label_visibility="collapsed",
    )
    if mode == "batch":
        _render_batch_mode(header=header, config=config)
        return

    render_section("input")
    uploaded_file = st.sidebar.file_uploader(
        "input_dir (one .docx or .pdf)",
        type=SUPPORTED_UPLOAD_TYPES,
        key=f"upload_{st.session_state['upload_counter']}",
    )

    provider, model, api_key = render_llm_controls(
        "chunker_single",
        default_model_for_provider=default_model_for_provider,
        env_fallback=False,
    )
    advanced = render_advanced_controls(
        "chunker_single",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    )

    if st.sidebar.button("clear / restart"):
        _restart_document_session()

    if uploaded_file is None:
        _clear_document_state()
        render_empty_state("Upload a `.docx` or `.pdf` document to begin.")
        return

    doc_id = Path(uploaded_file.name).stem
    file_bytes = uploaded_file.getvalue()
    file_suffix = _suffix_for_upload(uploaded_file)
    file_key = f"{uploaded_file.name}:{len(file_bytes)}"
    _reset_state_for_new_file(file_key)

    if st.sidebar.button("parse"):
        st.session_state.pop("blocks", None)
        with st.spinner("Parsing document..."):
            try:
                blocks = _parse_uploaded_file(file_bytes, doc_id, suffix=file_suffix)
                st.session_state["blocks"] = blocks
            except Exception as exc:
                st.error(f"Failed to parse document: {exc}")
                return

    blocks = st.session_state.get("blocks")
    if blocks is not None and st.sidebar.button("map"):
        if not api_key:
            st.error(f"Enter a {provider.title()} API key before running the mapper.")
        else:
            with st.spinner("Labeling blocks with mapper..."):
                _clear_block_labels(blocks)
                doc_id = blocks[0].doc_id if blocks else ""
                [pipeline_result] = map_blocks_batch(
                    [(doc_id, blocks)],
                    config=config,
                    llm_client_factory=lambda: create_llm_client(provider, api_key, model),
                    max_tokens=advanced["max_tokens"],
                    max_workers=1,
                )
                st.session_state["blocks"] = pipeline_result.blocks
                if pipeline_result.mapping_error:
                    st.error(f"Failed to run mapper: {pipeline_result.mapping_error}")

    block_dicts = blocks_to_dicts(blocks) if blocks is not None else None
    _render_lifecycle_status(uploaded_file.name, block_dicts)
    if block_dicts is None:
        return

    _render_summary(block_dicts)
    if _has_labels(block_dicts):
        _render_section_summary(block_dicts, config.section_taxonomy)
    _render_block_index(block_dicts)
    _render_blocks(block_dicts)
    _render_download(block_dicts, doc_id)


def _render_batch_mode(*, header, config) -> None:
    render_section("input")
    uploaded_files = st.sidebar.file_uploader(
        "input_dir (.docx, .pdf)",
        type=SUPPORTED_UPLOAD_TYPES,
        accept_multiple_files=True,
        key=f"batch_upload_{st.session_state['batch_upload_counter']}",
    )
    map_blocks = st.sidebar.checkbox(
        "map",
        value=False,
        help="Run the mapper to label blocks. CLI: --map",
        key="chunker_batch_map",
    )

    provider, model, api_key = render_llm_controls(
        "chunker_batch",
        default_model_for_provider=default_model_for_provider,
        env_fallback=False,
    )
    advanced = render_advanced_controls(
        "chunker_batch",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        show_max_workers=True,
    )

    if st.sidebar.button("clear / restart", key="batch_clear_restart"):
        _restart_document_session()

    if not uploaded_files:
        _clear_batch_state()
        render_empty_state("Upload one or more `.docx` or `.pdf` documents to begin.")
        return

    batch_key = "|".join(f"{file.name}:{file.size}" for file in uploaded_files)
    _reset_batch_state_for_new_files(batch_key)

    st.success(f"Uploaded {len(uploaded_files)} documents.")
    st.info("Click Parse All Documents to compare parser output across files.")

    if st.sidebar.button("parse"):
        st.session_state.pop("batch_results", None)
        with st.spinner("Parsing documents..."):
            try:
                st.session_state["batch_results"] = _parse_batch_files_parallel(
                    uploaded_files,
                    max_workers=advanced["max_workers"],
                )
            except Exception as exc:
                st.error(f"Failed to parse batch: {exc}")
                return

    batch_results = st.session_state.get("batch_results")
    if not batch_results:
        return

    st.success("Batch parsing completed.")
    if st.sidebar.button("map"):
        if not api_key:
            st.error(
                f"Enter a {provider.title()} API key before running the batch mapper."
            )
        else:
            with st.spinner("Mapping documents in parallel..."):
                batch_results = _clear_batch_labels(batch_results)
                st.session_state["batch_results"] = _map_batch_results_parallel(
                    batch_results,
                    config,
                    api_key,
                    provider,
                    model,
                    max_tokens=advanced["max_tokens"],
                    max_workers=advanced["max_workers"],
                )
                batch_results = st.session_state["batch_results"]

    if _batch_has_labels(batch_results):
        st.success("Batch mapping completed.")
    _render_batch_summary(batch_results)
    _render_batch_previews(batch_results)
    _render_batch_downloads(batch_results)


def _parse_uploaded_file(
    file_bytes: bytes,
    doc_id: str,
    suffix: str = ".docx",
) -> list[ContentBlock]:
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        return run_pipeline(temp_path, doc_id)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


SUPPORTED_UPLOAD_TYPES = ["docx", "pdf"]


def _suffix_for_upload(uploaded_file) -> str:
    return Path(uploaded_file.name).suffix.lower() or ".docx"


def _parse_batch_files_parallel(
    uploaded_files: list,
    max_workers: int = 4,
) -> list[dict]:
    """Parse uploaded files in parallel via the shared pipeline.

    Returns the legacy dict shape downstream rendering expects.
    """
    file_jobs = [_stage_upload(uploaded_file) for uploaded_file in uploaded_files]
    try:
        pipeline_jobs = [(stage["file_path"], stage["doc_id"]) for stage in file_jobs]
        results = run_pipeline_batch(
            pipeline_jobs,
            config=None,
            llm_client_factory=None,
            max_workers=max_workers,
        )
        return [
            _batch_dict_from_pipeline_result(stage["file_name"], pipeline_result)
            for stage, pipeline_result in zip(file_jobs, results)
        ]
    finally:
        for stage in file_jobs:
            if os.path.exists(stage["file_path"]):
                os.unlink(stage["file_path"])


def _map_batch_results_parallel(
    batch_results: list[dict],
    config,
    api_key: str,
    provider: str,
    model: str,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_workers: int = 4,
) -> list[dict]:
    """Map already-parsed batch results in parallel via the shared pipeline."""
    map_jobs = [
        (result["doc_id"], _rehydrate_blocks(result["blocks"]))
        for result in batch_results
    ]
    pipeline_results = map_blocks_batch(
        map_jobs,
        config=config,
        llm_client_factory=lambda: create_llm_client(provider, api_key, model),
        max_tokens=max_tokens,
        max_workers=max_workers,
    )
    return [
        _merge_mapped_into_batch_result(result, pipeline_result)
        for result, pipeline_result in zip(batch_results, pipeline_results)
    ]


def _stage_upload(uploaded_file) -> dict:
    """Write the upload to a temp file the caller is responsible for cleaning up."""
    doc_id = Path(uploaded_file.name).stem
    suffix = _suffix_for_upload(uploaded_file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = temp_file.name
    return {"file_path": temp_path, "doc_id": doc_id, "file_name": uploaded_file.name}


def _batch_dict_from_pipeline_result(file_name: str, pipeline_result) -> dict:
    block_dicts = blocks_to_dicts(pipeline_result.blocks)
    return {
        "doc_id": pipeline_result.doc_id,
        "file_name": file_name,
        "metrics": _batch_metrics(pipeline_result.doc_id, file_name, block_dicts),
        "blocks": block_dicts,
    }


def _rehydrate_blocks(block_dicts: list[dict]) -> list[ContentBlock]:
    blocks = [ContentBlock(**block) for block in block_dicts]
    _clear_block_labels(blocks)
    return blocks


def _merge_mapped_into_batch_result(result: dict, pipeline_result) -> dict:
    if pipeline_result.mapping_error:
        clean_blocks = _clear_block_dict_labels(result["blocks"])
        metrics = _batch_metrics(result["doc_id"], result["file_name"], clean_blocks)
        return {
            **result,
            "metrics": metrics,
            "blocks": clean_blocks,
            "mapper_error": pipeline_result.mapping_error,
        }
    block_dicts = blocks_to_dicts(pipeline_result.blocks)
    metrics = _batch_metrics(result["doc_id"], result["file_name"], block_dicts)
    metrics.update(_batch_label_metrics(block_dicts))
    return {
        **result,
        "metrics": metrics,
        "blocks": block_dicts,
        "mapper_error": None,
    }


def _clear_block_labels(blocks: list[ContentBlock]) -> list[ContentBlock]:
    for block in blocks:
        block.section_label = None
        block.label_confidence = None
    return blocks


def _clear_batch_labels(batch_results: list[dict]) -> list[dict]:
    return [
        {
            **result,
            "metrics": _batch_metrics(
                result["doc_id"],
                result["file_name"],
                _clear_block_dict_labels(result["blocks"]),
            ),
            "blocks": _clear_block_dict_labels(result["blocks"]),
            "mapper_error": None,
        }
        for result in batch_results
    ]


def _clear_block_dict_labels(blocks: list[dict]) -> list[dict]:
    clean_blocks = []
    for block in blocks:
        clean_block = dict(block)
        clean_block["section_label"] = None
        clean_block["label_confidence"] = None
        clean_blocks.append(clean_block)
    return clean_blocks


def _reset_state_for_new_file(file_key: str) -> None:
    if st.session_state.get("file_key") != file_key:
        st.session_state["file_key"] = file_key
        st.session_state.pop("blocks", None)


def _clear_document_state() -> None:
    st.session_state.pop("file_key", None)
    st.session_state.pop("blocks", None)


def _reset_batch_state_for_new_files(batch_key: str) -> None:
    if st.session_state.get("batch_key") != batch_key:
        st.session_state["batch_key"] = batch_key
        st.session_state.pop("batch_results", None)


def _clear_batch_state() -> None:
    st.session_state.pop("batch_key", None)
    st.session_state.pop("batch_results", None)


def _restart_document_session() -> None:
    _clear_document_state()
    _clear_batch_state()
    st.session_state["upload_counter"] += 1
    st.session_state["batch_upload_counter"] += 1
    st.session_state.pop("api_key", None)
    st.session_state.pop("single_anthropic_api_key", None)
    st.session_state.pop("single_openai_api_key", None)
    st.session_state.pop("batch_anthropic_api_key", None)
    st.session_state.pop("batch_openai_api_key", None)
    st.rerun()


def _render_lifecycle_status(file_name: str, blocks: list[dict] | None) -> None:
    st.success(f"Uploaded: {file_name}")
    if blocks is None:
        st.info("Click **Parse Document** to extract ContentBlocks.")
        return
    if _has_labels(blocks):
        st.success("Parsed and labeled. Blocks include section labels.")
        return
    st.success("Parsed. Optionally click **Run Mapper** to label blocks.")


def _render_summary(blocks: list[dict]) -> None:
    st.subheader("Parser Output: ContentBlocks")
    counts = Counter(block["source_type"] for block in blocks)
    columns = st.columns(4)
    columns[0].metric("Total blocks", len(blocks))
    columns[1].metric("Headings", counts.get("heading", 0))
    columns[2].metric("Paragraphs", counts.get("paragraph", 0))
    columns[3].metric("Table rows", counts.get("table_row", 0))


def _render_batch_summary(batch_results: list[dict]) -> None:
    st.subheader("Batch Overview")
    st.caption(
        "Scan this table first to spot documents that need closer inspection."
    )
    st.dataframe(_batch_overview_rows(batch_results), width="stretch", hide_index=True)

    mapper_errors = [
        {
            "doc_id": result["doc_id"],
            "file_name": result["file_name"],
            "mapper_error": result["mapper_error"],
        }
        for result in batch_results
        if result.get("mapper_error")
    ]
    if mapper_errors:
        st.subheader("Batch Mapper Errors")
        st.dataframe(mapper_errors, width="stretch")


def _batch_overview_rows(batch_results: list[dict]) -> list[dict]:
    rows = []
    for result in batch_results:
        metrics = result["metrics"]
        is_mapped = _has_labels(result["blocks"])
        rows.append(
            {
                "doc": result["file_name"],
                "blocks": metrics["total_blocks"],
                "headings": metrics["heading_count"],
                "table_rows": metrics["table_row_count"],
                "layout_table_blocks": metrics["single_column_table_blocks"],
                "map_status": _batch_result_status(result),
                "metadata": metrics.get("document_metadata_count", 0),
                "mapping_errors": metrics.get("mapping_error_count", 0),
                "low_conf": metrics.get("low_confidence_count", 0),
                "avg_conf": metrics.get("average_confidence", "") if is_mapped else "",
            }
        )
    return rows


def _batch_result_status(result: dict) -> str:
    if result.get("mapper_error"):
        return "mapper error"
    if _has_labels(result["blocks"]):
        return "mapped"
    return "parsed"


def _render_batch_previews(batch_results: list[dict]) -> None:
    st.subheader("Per-Document Validation")
    st.caption(
        "Open a document to inspect parser shape, section distribution, and the block list."
    )
    for result in batch_results:
        metrics = result["metrics"]
        title = (
            f"{result['file_name']} | {_batch_result_status(result)} | "
            f"{metrics['total_blocks']} blocks"
        )

        with st.expander(title):
            if result.get("mapper_error"):
                st.error(result["mapper_error"])

            if _has_labels(result["blocks"]):
                st.markdown("**Section Distribution**")
                st.dataframe(_section_distribution_rows(result["blocks"]), width="stretch")

            st.markdown("**Block Validation List**")
            _render_batch_block_validation_list(result["blocks"])

            with st.expander("Show full ContentBlock JSON"):
                _render_batch_block_details(result["blocks"])


def _render_batch_downloads(batch_results: list[dict]) -> None:
    st.subheader("Batch Downloads")
    summary_rows = [result["metrics"] for result in batch_results]
    columns = st.columns(2)
    columns[0].download_button(
        label="Download Batch Summary CSV",
        data=_dicts_to_csv(summary_rows),
        file_name="batch_summary.csv",
        mime="text/csv",
    )
    columns[1].download_button(
        label="Download Combined Blocks JSON",
        data=json.dumps(batch_results, indent=2),
        file_name="batch_blocks.json",
        mime="application/json",
    )


def _section_distribution_rows(blocks: list[dict]) -> list[dict]:
    grouped_blocks = defaultdict(list)
    for block in blocks:
        grouped_blocks[block["section_label"] or "Unlabeled"].append(block)

    return [
        {
            "section_label": section_label,
            "block_count": len(section_blocks),
            "average_confidence": _average_confidence(section_blocks),
        }
        for section_label, section_blocks in grouped_blocks.items()
    ]


def _render_batch_block_validation_list(blocks: list[dict]) -> None:
    rows = [_batch_block_validation_row(block) for block in blocks]
    st.dataframe(rows, width="stretch", hide_index=True)


def _batch_block_validation_row(block: dict) -> dict:
    return {
        "#": block["ordinal"],
        "section": block["section_label"] or "Not mapped yet",
        "confidence": block["label_confidence"] or "",
        "type": block["source_type"],
        "heading": _current_heading(block["heading_stack"]),
        "content": _truncate(_compact_text(block["content"]), 220),
    }


def _render_batch_block_details(blocks: list[dict]) -> None:
    for block in blocks:
        title = (
            f"{block['ordinal']:04d} | {block['source_type']} | "
            f"{block['section_label'] or 'not mapped yet'} | "
            f"{_truncate(block['content'], 80)}"
        )
        with st.expander(title):
            st.markdown("**Content**")
            st.text(block["content"])
            st.markdown("**Full ContentBlock JSON**")
            st.json(block)


def _current_heading(heading_stack: list[str]) -> str:
    if not heading_stack:
        return ""
    return heading_stack[-1]


def _compact_text(value: str) -> str:
    return " ".join(value.split())


def _render_section_summary(blocks: list[dict], section_taxonomy: list[dict]) -> None:
    st.subheader("Mapper Output: Section Labels")
    section_blocks = defaultdict(list)
    for block in blocks:
        section_blocks[block["section_label"] or "Unlabeled"].append(block)

    section_labels = [section["name"] for section in section_taxonomy]
    section_labels.extend(
        label for label in section_blocks if label not in section_labels
    )

    rows = []
    for section_label in section_labels:
        grouped_blocks = section_blocks[section_label]
        rows.append(
            {
                "section_label": section_label,
                "block_count": len(grouped_blocks),
                "average_confidence": _average_confidence(grouped_blocks),
            }
        )
    st.dataframe(rows, width="stretch")


def _render_block_index(blocks: list[dict]) -> None:
    if _has_labels(blocks):
        st.subheader("Labeled Block Index")
    else:
        st.subheader("Parser Block Index")
    rows = [
        {
            "id": block["id"],
            "ordinal": block["ordinal"],
            "source_type": block["source_type"],
            "section_label": block["section_label"],
            "heading_stack": " > ".join(block["heading_stack"]),
            "content": _truncate(block["content"], 100),
        }
        for block in blocks
    ]
    st.dataframe(rows, width="stretch")


def _render_blocks(blocks: list[dict]) -> None:
    if _has_labels(blocks):
        st.subheader("Labeled Blocks by Section")
        grouped_blocks = defaultdict(list)
        for block in blocks:
            grouped_blocks[block["section_label"] or "Unlabeled"].append(block)

        for section_label, section_blocks in grouped_blocks.items():
            st.markdown(f"### {section_label}")
            for block in section_blocks:
                _render_block(block)
        return

    st.subheader("Parser Blocks")
    for block in blocks:
        _render_block(block)


def _render_block(block: dict) -> None:
    title = f"{block['id']} | {block['source_type']} | {_truncate(block['content'], 80)}"
    with st.expander(title):
        st.markdown("**Content**")
        st.text(block["content"])
        st.markdown("**Full ContentBlock JSON**")
        st.json(block)


def _render_download(blocks: list[dict], doc_id: str) -> None:
    st.download_button(
        label="Download JSON",
        data=json.dumps(blocks, indent=2),
        file_name=f"{doc_id}_blocks.json",
        mime="application/json",
    )


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _batch_metrics(doc_id: str, file_name: str, blocks: list[dict]) -> dict:
    source_counts = Counter(block["source_type"] for block in blocks)
    style_sources = Counter(
        block["style_hint"].get("source")
        for block in blocks
        if block["style_hint"].get("source")
    )
    table_indexes = {
        block["structural_meta"]["table_index"]
        for block in blocks
        if "table_index" in block["structural_meta"]
    }
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "total_blocks": len(blocks),
        "heading_count": source_counts.get("heading", 0),
        "paragraph_count": source_counts.get("paragraph", 0),
        "table_row_count": source_counts.get("table_row", 0),
        "single_column_table_blocks": style_sources.get("single_column_table", 0),
        "single_cell_table_blocks": style_sources.get("single_cell_table", 0),
        "table_count": len(table_indexes),
        "has_headings": source_counts.get("heading", 0) > 0,
        "has_tables": len(table_indexes) > 0,
    }


def _batch_label_metrics(blocks: list[dict]) -> dict:
    section_counts = Counter(
        block["section_label"]
        for block in blocks
        if block["section_label"] is not None
    )
    confidence_counts = Counter(
        block["label_confidence"]
        for block in blocks
        if block["label_confidence"] is not None
    )
    return {
        "unlabeled_count": sum(
            1 for block in blocks if block["section_label"] is None
        ),
        "mapping_error_count": section_counts.get("Mapping Error", 0),
        "document_metadata_count": section_counts.get("Document Metadata", 0),
        "low_confidence_count": confidence_counts.get("low", 0),
        "medium_confidence_count": confidence_counts.get("medium", 0),
        "high_confidence_count": confidence_counts.get("high", 0),
        "average_confidence": _average_confidence(blocks),
    }


def _batch_has_labels(batch_results: list[dict]) -> bool:
    return any(_has_labels(result["blocks"]) for result in batch_results)


def _dicts_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""

    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _has_labels(blocks: list[dict]) -> bool:
    return any(block["section_label"] is not None for block in blocks)


def _average_confidence(blocks: list[dict]) -> str:
    confidence_scores = {"low": 1, "medium": 2, "high": 3}
    scores = [
        confidence_scores.get(block["label_confidence"], 1)
        for block in blocks
        if block["label_confidence"] is not None
    ]
    if not scores:
        return "n/a"

    average = sum(scores) / len(scores)
    if average >= 2.5:
        return "high"
    if average >= 1.5:
        return "medium"
    return "low"


if __name__ == "__main__":
    main()
