"""Streamlit entry for the PDIS tool suite.

Run from the repo root:
    streamlit run tools/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

from tools.chunker_tool import render as render_chunker  # noqa: E402
from tools.evidence_tool import render as render_evidence  # noqa: E402
from tools.pd_reviewer_tool import render as render_pd_reviewer  # noqa: E402


def main() -> None:
    st.set_page_config(page_title="PDIS Tools", layout="wide")

    tool = st.sidebar.selectbox(
        "Tool",
        [
            "Chunker",
            "Evidence",
            "PD Reviewer",
        ],
    )

    if tool == "Chunker":
        render_chunker()
        return

    if tool == "Evidence":
        render_evidence()
        return

    render_pd_reviewer()


if __name__ == "__main__":
    main()
