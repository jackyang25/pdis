from __future__ import annotations

import streamlit as st

from chunker.interface import render as render_chunker
from evidence.interface import render as render_evidence
from pd_reviewer.interface import render as render_pd_reviewer


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
