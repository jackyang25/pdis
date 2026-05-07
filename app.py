from __future__ import annotations

import streamlit as st

from chunker.app import render as render_chunker
from pd_reviewer.app import render as render_pd_reviewer


def main() -> None:
    st.set_page_config(page_title="PDIS Tools", layout="wide")

    tool = st.sidebar.selectbox(
        "Tool",
        [
            "Document Chunker",
            "PD Reviewer",
        ],
    )

    if tool == "Document Chunker":
        render_chunker()
        return

    render_pd_reviewer()


if __name__ == "__main__":
    main()
