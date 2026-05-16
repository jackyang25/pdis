from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until requirements are installed
    def load_dotenv() -> None:
        return None

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pd_reviewer.pipeline import review_document  # noqa: E402
from pd_reviewer.llm_client import (  # noqa: E402
    create_llm_client,
    default_model_for_provider,
)
from pd_reviewer.models import (  # noqa: E402
    ReviewConfig,
    ReviewResult,
    load_review_config,
    review_result_to_dict,
)

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
    st.title("PD Reviewer")

    if "pd_reviewer_upload_counter" not in st.session_state:
        st.session_state["pd_reviewer_upload_counter"] = 0

    _render_sidebar()
    result = st.session_state.get("pd_reviewer_result")
    if result is None:
        st.info("Upload a document `.docx`, enter an API key, and run the review.")
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

    provider, model, api_key = _render_llm_controls("pd_reviewer")

    if st.sidebar.button("Run Review"):
        if uploaded_file is None:
            st.error("Upload a `.docx` document before running the review.")
        elif not api_key:
            st.error(f"Enter a {provider.title()} API key before running the review.")
        else:
            _run_review(uploaded_file, config, api_key, provider, model)

    if st.sidebar.button("Clear / Restart"):
        _restart_review_session()

    return config


def _restart_review_session() -> None:
    st.session_state.pop("pd_reviewer_result", None)
    st.session_state["pd_reviewer_upload_counter"] += 1
    st.rerun()


def _load_available_configs() -> dict[str, ReviewConfig]:
    config_dir = Path(__file__).parent / "configs"
    config_paths = sorted(config_dir.glob("*.yaml"))
    if not config_paths:
        raise FileNotFoundError(f"No PD Reviewer configs found in {config_dir}")

    configs = [load_review_config(str(path)) for path in config_paths]
    return {config.display_name: config for config in configs}


def _render_llm_controls(key_prefix: str) -> tuple[str, str, str]:
    provider = st.sidebar.selectbox(
        "LLM provider",
        ["anthropic", "openai"],
        key=f"{key_prefix}_llm_provider",
    )
    model = st.sidebar.text_input(
        "Model",
        value=default_model_for_provider(provider),
        key=f"{key_prefix}_llm_model_{provider}",
    )
    api_label = "Anthropic API key" if provider == "anthropic" else "OpenAI API key"
    env_key = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    api_key = st.sidebar.text_input(
        api_label,
        value=os.environ.get(env_key, ""),
        type="password",
        key=f"{key_prefix}_{provider}_api_key",
    )
    return provider, model, api_key


def _run_review(
    uploaded_file,
    config: ReviewConfig,
    api_key: str,
    provider: str,
    model: str,
) -> None:
    doc_id = Path(uploaded_file.name).stem
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            temp_file.write(uploaded_file.getvalue())
            temp_path = temp_file.name

        with st.spinner("Reviewing document..."):
            llm_client = create_llm_client(provider, api_key, model)
            result = review_document(temp_path, config, llm_client)
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
