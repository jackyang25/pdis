"""Per-result-type semantic legends for the Ask assistant.

The navigator is fully generic (JSON tree in, slices out); this registry is the
ONE place that carries each result type's meaning. The agent's system prompt
includes the legend so it can interpret the otherwise-opaque tree.

Adding a new doc type = add one entry here. No navigator/agent changes.
"""

from __future__ import annotations

SCOUT_LEGEND = """This is a SCOUT result: a TPP's targets tested against real-world web/literature/registry evidence. Shape:
- variables[]: the TPP attributes analyzed (name, description).
- matches[]: each is one web-derived insight + its relation to the document:
    contradicts = evidence shows the target is disproven/unachievable, or a stated fact is wrong;
    extends = adds info / the current standard differs from an aspirational target (a gap, not a failure);
    confirms = supports the target; unrelated = off-topic. Each insight carries supporting_findings (url, title, excerpt, source).
- conformity[]: per quantitative variable, a 0-1 likelihood the target is MET by current evidence (with lower/upper band, verdict, measurements). LOW is not "bad" - it often means an ambitious/stretch target above today's evidence.
- precedents[]: per variable, whether the approach has been tried: established / emerging / novel (white space) / disconfirmed (tried & failed) / unknown.
- assessments[]: per variable, weight-of-evidence strength (well_grounded/partial/thin/unsupported/unknown) + basis + doc_target.
- stats: funnel counts."""

REVIEWER_LEGEND = """This is a REVIEWER result: a document graded inward against its rubric. Shape:
- dimensions: document-level grades (A-F) on completeness (is content present?), adherence (does it follow the rubric's structure/format?), rigor (is the content specific, measurable, sound?).
- section_grades[]: per section - is_present, the three dimension grades (each with issues[] and a recommendation), missing_variables[], and variable_grades[] (per-variable dimension grades).
- cross_section_findings[]: contradictions that span MULTIPLE sections (description, the sections involved, a recommendation).
- top_issues[]: the most severe issues across the document."""

_LEGENDS: dict[str, str] = {
    "scout": SCOUT_LEGEND,
    "reviewer": REVIEWER_LEGEND,
}


def legend_for(result_type: str) -> str:
    """Return the semantic legend for a result type, or a neutral fallback."""
    return _LEGENDS.get(
        result_type,
        "This is a structured analysis result. Navigate it as a JSON tree.",
    )
