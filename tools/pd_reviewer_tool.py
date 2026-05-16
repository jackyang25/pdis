from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until requirements are installed
    def load_dotenv() -> None:
        return None

from pd_reviewer.pipeline import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    run_pipeline,
    run_pipeline_batch,
)
from pd_reviewer.models import (  # noqa: E402
    BatchReviewResult,
    ReviewConfig,
    ReviewResult,
    load_review_config,
    review_result_to_dict,
)
from llm_client import create_llm_client, default_model_for_provider  # noqa: E402
from tools._ui import render_empty_state, render_header, render_advanced_controls, render_llm_controls  # noqa: E402


GRADE_COLORS = {
    "A": "#2e7d32",
    "B": "#2e7d32",
    "C": "#f9a825",
    "D": "#c62828",
    "F": "#c62828",
    "N/A": "#616161",
}


def main() -> None:
    st.set_page_config(page_title="PD Reviewer", layout="wide")
    render()


def render() -> None:
    """Render the PD Reviewer UI inside a Streamlit app."""
    load_dotenv()
    render_header(
        "PD Reviewer",
        "Rubric Grading",
        caption="Grade a PD document against a TPP rubric. "
        "Returns an overall grade, top issues, and section-level breakdown.",
    )

    if "pd_reviewer_upload_counter" not in st.session_state:
        st.session_state["pd_reviewer_upload_counter"] = 0
    if "pd_reviewer_batch_upload_counter" not in st.session_state:
        st.session_state["pd_reviewer_batch_upload_counter"] = 0

    mode = st.sidebar.selectbox("Mode", ["Single Document", "Batch"])
    if mode == "Batch":
        _render_batch_mode()
        return

    _render_single_mode()


def _render_single_mode() -> None:
    _render_sidebar()
    result = st.session_state.get("pd_reviewer_result")
    if result is None:
        render_empty_state("Upload a `.docx` document to begin.")
        return

    _render_result(result)


def _render_sidebar() -> ReviewConfig:
    configs = _load_available_configs()
    config_labels = list(configs.keys())
    selected_label = st.sidebar.selectbox("Document type", config_labels)
    config = configs[selected_label]

    uploaded_file = st.sidebar.file_uploader(
        "Upload document",
        type=["docx"],
        key=f"pd_reviewer_upload_{st.session_state['pd_reviewer_upload_counter']}",
    )

    provider, model, api_key = render_llm_controls(
        "pd_reviewer",
        default_model_for_provider=default_model_for_provider,
    )
    advanced = render_advanced_controls(
        "pd_reviewer",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    )

    if st.sidebar.button("Run Review"):
        if uploaded_file is None:
            st.error("Upload a `.docx` document before running the review.")
        elif not api_key:
            st.error(f"Enter a {provider.title()} API key before running the review.")
        else:
            _run_review(
                uploaded_file,
                config,
                api_key,
                provider,
                model,
                max_tokens=advanced["max_tokens"],
            )

    if st.sidebar.button("Clear / Restart"):
        _restart_review_session()

    return config


def _render_batch_mode() -> None:
    configs = _load_available_configs()
    selected_label = st.sidebar.selectbox(
        "Document type", list(configs.keys()), key="pd_batch_doc_type"
    )
    config = configs[selected_label]

    uploaded_files = st.sidebar.file_uploader(
        "Upload documents (.docx)",
        type=["docx"],
        accept_multiple_files=True,
        key=f"pd_reviewer_batch_upload_{st.session_state['pd_reviewer_batch_upload_counter']}",
    )

    provider, model, api_key = render_llm_controls(
        "pd_reviewer_batch",
        default_model_for_provider=default_model_for_provider,
    )
    advanced = render_advanced_controls(
        "pd_reviewer_batch",
        default_max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        show_max_workers=True,
    )

    if st.sidebar.button("Run Batch Review"):
        if not uploaded_files:
            st.error("Upload one or more `.docx` documents before running.")
        elif not api_key:
            st.error(f"Enter a {provider.title()} API key before running.")
        else:
            _run_batch_review(
                uploaded_files,
                config,
                api_key,
                provider,
                model,
                max_tokens=advanced["max_tokens"],
                max_workers=advanced["max_workers"],
            )

    if st.sidebar.button("Clear / Restart", key="pd_batch_clear_restart"):
        _restart_review_session()

    batch_results = st.session_state.get("pd_reviewer_batch_results")
    if not batch_results:
        render_empty_state("Upload one or more `.docx` documents to begin.")
        return

    _render_batch_results(batch_results)


def _run_batch_review(
    uploaded_files,
    config: ReviewConfig,
    api_key: str,
    provider: str,
    model: str,
    *,
    max_tokens: int,
    max_workers: int,
) -> None:
    staged = [_stage_upload(file) for file in uploaded_files]
    try:
        jobs = [(stage["file_path"], stage["doc_key"]) for stage in staged]
        with st.spinner(f"Reviewing {len(jobs)} documents..."):
            results = run_pipeline_batch(
                jobs,
                config=config,
                llm_client_factory=lambda: create_llm_client(provider, api_key, model),
                max_tokens=max_tokens,
                max_workers=max_workers,
            )
        st.session_state["pd_reviewer_batch_results"] = results
    finally:
        for stage in staged:
            if os.path.exists(stage["file_path"]):
                os.unlink(stage["file_path"])


def _stage_upload(uploaded_file) -> dict:
    doc_key = Path(uploaded_file.name).stem
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        temp_file.write(uploaded_file.getvalue())
        return {"file_path": temp_file.name, "doc_key": doc_key}


def _render_batch_results(batch_results: list[BatchReviewResult]) -> None:
    succeeded = [r for r in batch_results if r.review is not None]
    failed = [r for r in batch_results if r.error is not None]
    st.success(f"Reviewed {len(succeeded)} of {len(batch_results)} documents.")

    if failed:
        with st.expander(f"Failures ({len(failed)})"):
            for result in failed:
                st.error(f"{result.doc_key}: {result.error}")

    st.subheader("Batch Overview")
    st.dataframe(
        [
            {
                "doc": r.doc_key,
                "overall_grade": r.review.overall_grade if r.review else "—",
                "top_issues": len(r.review.top_issues) if r.review else 0,
                "status": "ok" if r.review else "error",
            }
            for r in batch_results
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Per-Document Reviews")
    for result in batch_results:
        if result.review is None:
            continue
        with st.expander(f"{result.doc_key} — {result.review.overall_grade}"):
            _render_result(result.review)

    st.subheader("Downloads")
    payload = [
        review_result_to_dict(r.review) if r.review else {"doc_key": r.doc_key, "error": r.error}
        for r in batch_results
    ]
    st.download_button(
        "Download All Reviews (JSON)",
        data=json.dumps(payload, indent=2),
        file_name="batch_reviews.json",
        mime="application/json",
    )


def _restart_review_session() -> None:
    st.session_state.pop("pd_reviewer_result", None)
    st.session_state.pop("pd_reviewer_batch_results", None)
    st.session_state["pd_reviewer_upload_counter"] += 1
    st.session_state["pd_reviewer_batch_upload_counter"] += 1
    st.rerun()


def _load_available_configs() -> dict[str, ReviewConfig]:
    config_dir = ROOT_DIR / "pd_reviewer" / "configs"
    config_paths = sorted(config_dir.glob("*.yaml"))
    if not config_paths:
        raise FileNotFoundError(f"No PD Reviewer configs found in {config_dir}")

    configs = [load_review_config(str(path)) for path in config_paths]
    return {config.display_name: config for config in configs}


def _run_review(
    uploaded_file,
    config: ReviewConfig,
    api_key: str,
    provider: str,
    model: str,
    *,
    max_tokens: int,
) -> None:
    doc_id = Path(uploaded_file.name).stem
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            temp_file.write(uploaded_file.getvalue())
            temp_path = temp_file.name

        with st.spinner("Reviewing document..."):
            llm_client = create_llm_client(provider, api_key, model)
            result = run_pipeline(
                temp_path,
                config=config,
                llm_client=llm_client,
                max_tokens=max_tokens,
            )
            result.doc_id = doc_id
            st.session_state["pd_reviewer_result"] = result
    except Exception as exc:
        st.session_state.pop("pd_reviewer_result", None)
        st.error(f"Review failed: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _render_result(result: ReviewResult) -> None:
    _render_overall_grade(result)
    _render_top_issues(result)
    _render_section_breakdown(result)
    _render_download(result)


def _render_overall_grade(result: ReviewResult) -> None:
    color = GRADE_COLORS.get(result.overall_grade, "#616161")
    st.markdown(
        f"""
        <div style="padding: 1rem; border-radius: .5rem; background: {color}; color: white;">
          <div style="font-size: 1rem;">Overall Grade</div>
          <div style="font-size: 3rem; font-weight: 700;">{result.overall_grade}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_top_issues(result: ReviewResult) -> None:
    st.subheader("Top Issues")
    if not result.top_issues:
        st.success("No major issues were identified.")
        return
    for issue in result.top_issues:
        st.warning(issue)


def _render_section_breakdown(result: ReviewResult) -> None:
    st.subheader("Section Breakdown")
    for section_grade in result.section_grades:
        with st.expander(
            f"{section_grade.section_name} - {section_grade.grade}",
            expanded=section_grade.grade in {"D", "F"},
        ):
            st.write(f"**Present:** {'Yes' if section_grade.is_present else 'No'}")
            _render_list("Issues", section_grade.issues)
            st.write(f"**Recommendation:** {section_grade.recommendation}")
            if section_grade.variable_grades:
                st.write("**Variable Grades**")
                st.dataframe(
                    [
                        {
                            "Variable": variable.variable_name,
                            "Grade": variable.grade,
                            "Issues": "; ".join(variable.issues),
                            "Recommendation": variable.recommendation,
                            "Block IDs": ", ".join(variable.block_ids),
                        }
                        for variable in section_grade.variable_grades
                    ],
                    use_container_width=True,
                )


def _render_list(title: str, items: list[str]) -> None:
    st.write(f"**{title}:**")
    if not items:
        st.write("None.")
        return
    for item in items:
        st.write(f"- {item}")


def _render_download(result: ReviewResult) -> None:
    result_json = json.dumps(review_result_to_dict(result), indent=2)
    st.download_button(
        "Download Full Review JSON",
        data=result_json,
        file_name=f"{result.doc_id}_review.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
