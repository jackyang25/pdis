from __future__ import annotations

import streamlit as st

from chunker.app import render as render_chunker
from quality_assessment.app import render as render_quality_assessment


def main() -> None:
    st.set_page_config(page_title="PDIS Tools", layout="wide")

    tool = st.sidebar.selectbox(
        "Tool",
        [
            "Document Chunker",
            "Document Quality Assessment",
        ],
    )

    if tool == "Document Chunker":
        render_chunker()
        return

    render_quality_assessment()


if __name__ == "__main__":
    main()
