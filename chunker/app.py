from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import streamlit as st

try:
    from .mapper import label_blocks
    from .models import ContentBlock, blocks_to_dicts, load_config
    from .parser import parse_document
except ImportError:  # pragma: no cover - supports `streamlit run chunker/app.py`
    from mapper import label_blocks
    from models import ContentBlock, blocks_to_dicts, load_config
    from parser import parse_document


def main() -> None:
    st.set_page_config(page_title="Document Chunker - Block Inspector", layout="wide")
    st.title("Document Chunker — Block Inspector")

    if "upload_counter" not in st.session_state:
        st.session_state["upload_counter"] = 0

    if st.sidebar.button("Clear / Restart"):
        _restart_document_session()

    uploaded_file = st.sidebar.file_uploader(
        "Upload a .docx file",
        type=["docx"],
        key=f"docx_upload_{st.session_state['upload_counter']}",
    )
    config_path = _config_path("tpp_vaccine.yaml")
    config = load_config(config_path)
    st.sidebar.selectbox("Document type", [config.display_name])
    api_key = st.sidebar.text_input("Anthropic API key", type="password", key="api_key")

    if uploaded_file is None:
        _clear_document_state()
        st.info("Step 1: Upload a .docx file to begin.")
        return

    doc_id = Path(uploaded_file.name).stem
    file_bytes = uploaded_file.getvalue()
    file_key = f"{uploaded_file.name}:{len(file_bytes)}"
    _reset_state_for_new_file(file_key)

    if st.sidebar.button("Parse Document"):
        with st.spinner("Parsing document..."):
            try:
                blocks = _parse_uploaded_file(file_bytes, doc_id)
                st.session_state["blocks"] = blocks
            except Exception as exc:
                st.error(f"Failed to parse document: {exc}")
                return

    blocks = st.session_state.get("blocks")
    if blocks is not None and st.sidebar.button("Run Mapper"):
        if not api_key:
            st.error("Enter an Anthropic API key before running the mapper.")
        else:
            with st.spinner("Labeling blocks with mapper..."):
                try:
                    blocks = label_blocks(blocks, config, api_key)
                    st.session_state["blocks"] = blocks
                except Exception as exc:
                    st.error(f"Failed to run mapper: {exc}")

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


def _parse_uploaded_file(file_bytes: bytes, doc_id: str) -> list[ContentBlock]:
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        return parse_document(temp_path, doc_id)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _reset_state_for_new_file(file_key: str) -> None:
    if st.session_state.get("file_key") != file_key:
        st.session_state["file_key"] = file_key
        st.session_state.pop("blocks", None)


def _clear_document_state() -> None:
    st.session_state.pop("file_key", None)
    st.session_state.pop("blocks", None)


def _restart_document_session() -> None:
    _clear_document_state()
    st.session_state["upload_counter"] += 1
    st.session_state.pop("api_key", None)
    st.rerun()


def _config_path(file_name: str) -> str:
    return str(Path(__file__).parent / "configs" / file_name)


def _render_lifecycle_status(file_name: str, blocks: list[dict] | None) -> None:
    st.success(f"Uploaded: {file_name}")
    if blocks is None:
        st.info("Step 2: Click Parse Document to extract ContentBlocks.")
        return

    st.success("Parsing completed.")
    if _has_labels(blocks):
        st.success("Mapper completed.")
        st.success("Status: Parsed and mapped. Blocks now include section labels.")
        return

    st.info("Status: Parsed, not mapped yet. Blocks are raw parser output.")
    st.info("Step 3: Optionally enter an API key and click Run Mapper.")


def _render_summary(blocks: list[dict]) -> None:
    st.subheader("Parser Output: ContentBlocks")
    counts = Counter(block["source_type"] for block in blocks)
    columns = st.columns(4)
    columns[0].metric("Total blocks", len(blocks))
    columns[1].metric("Headings", counts.get("heading", 0))
    columns[2].metric("Paragraphs", counts.get("paragraph", 0))
    columns[3].metric("Table rows", counts.get("table_row", 0))


def _render_section_summary(blocks: list[dict], section_taxonomy: list[str]) -> None:
    st.subheader("Mapper Output: Section Labels")
    section_blocks = defaultdict(list)
    for block in blocks:
        section_blocks[block["section_label"] or "Unlabeled"].append(block)

    section_labels = list(section_taxonomy)
    section_labels.extend(
        label for label in section_blocks if label not in section_taxonomy
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
