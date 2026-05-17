"""Streamlit entry for the PDIS tool suite.

Sidebar inputs mirror CLI flag names 1:1. Run from the repo root:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

from services.chunker import find_config as find_chunker_config  # noqa: E402
from services.evidence import find_config as find_evidence_config  # noqa: E402
from services.pd_reviewer import find_config as find_pd_reviewer_config  # noqa: E402

from dashboard._ui import render_section  # noqa: E402
from dashboard.chunker_tool import render as render_chunker  # noqa: E402
from dashboard.evidence_tool import render as render_evidence  # noqa: E402
from dashboard.pd_reviewer_tool import render as render_pd_reviewer  # noqa: E402


def main() -> None:
    st.set_page_config(page_title="PDIS Tools", layout="wide")

    header = _render_document_section()
    if header is None:
        st.info("Pick org / source_type / intervention in the sidebar to begin.")
        return

    render_section("tool")
    tool = st.sidebar.selectbox(
        "tool",
        ["chunker", "evidence", "pd_reviewer"],
        label_visibility="collapsed",
    )
    st.sidebar.markdown("---")

    if tool == "chunker":
        config = find_chunker_config(
            header["org"], header["source_type"], header["intervention_class"]
        )
        render_chunker(header=header, config=config)
    elif tool == "evidence":
        config = find_evidence_config(header["intervention_class"])
        render_evidence(header=header, config=config)
    else:
        config = find_pd_reviewer_config(
            header["org"], header["source_type"], header["intervention_class"]
        )
        render_pd_reviewer(header=header, config=config)


def _render_document_section() -> dict | None:
    """Sidebar `document` section. Returns the header dict or None."""
    render_section("document")

    orgs, source_types_by_org, interventions_by_org_source = _discover_chunker_triples()
    if not orgs:
        st.sidebar.error("No chunker configs found.")
        return None

    org = st.sidebar.selectbox("org", orgs, key="pdis_org")
    source_types = source_types_by_org.get(org, [])
    if not source_types:
        st.sidebar.error(f"No source_types available for org={org}.")
        return None

    source_type = st.sidebar.selectbox(
        "source_type", source_types, key=f"pdis_source_type_{org}"
    )
    interventions = interventions_by_org_source.get((org, source_type), [])
    if not interventions:
        st.sidebar.error(
            f"No interventions available for ({org}, {source_type})."
        )
        return None

    intervention = st.sidebar.selectbox(
        "intervention", interventions, key=f"pdis_intervention_{org}_{source_type}"
    )

    therapeutic_areas = _therapeutic_areas_for_intervention(intervention)
    therapeutic_area = (
        st.sidebar.selectbox(
            "therapeutic_area",
            [""] + therapeutic_areas,
            key=f"pdis_therapeutic_area_{intervention}",
            help="optional. CLI: --therapeutic-area",
        )
        or None
    )

    st.sidebar.markdown("---")

    return {
        "org": org,
        "source_type": source_type,
        "intervention_class": intervention,
        "therapeutic_area": therapeutic_area,
    }


def _discover_chunker_triples():
    """Discover available header triples from chunker/configs/ filenames.

    Returns (orgs, source_types_by_org, interventions_by_(org, source_type)).
    """
    configs_dir = ROOT_DIR / "chunker" / "configs"
    triples: set[tuple[str, str, str]] = set()
    for path in sorted(configs_dir.glob("*.yaml")):
        if "TEMPLATE" in path.stem.upper():
            continue
        parts = path.stem.split("_")
        if len(parts) < 3:
            continue
        triples.add((parts[0], parts[1], "_".join(parts[2:])))

    orgs = sorted({org for org, _, _ in triples})
    source_types_by_org: dict[str, list[str]] = {}
    interventions_by_org_source: dict[tuple[str, str], list[str]] = {}
    for org, source_type, intervention in triples:
        source_types_by_org.setdefault(org, [])
        if source_type not in source_types_by_org[org]:
            source_types_by_org[org].append(source_type)
        interventions_by_org_source.setdefault((org, source_type), [])
        if intervention not in interventions_by_org_source[(org, source_type)]:
            interventions_by_org_source[(org, source_type)].append(intervention)
    for values in source_types_by_org.values():
        values.sort()
    for values in interventions_by_org_source.values():
        values.sort()
    return orgs, source_types_by_org, interventions_by_org_source


def _therapeutic_areas_for_intervention(intervention: str) -> list[str]:
    """Read therapeutic_areas from the evidence config for this intervention."""
    try:
        config = find_evidence_config(intervention)
        return list(config.therapeutic_areas)
    except LookupError:
        return []


if __name__ == "__main__":
    main()
