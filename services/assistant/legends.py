"""Per-result-type semantic legends for the Ask assistant.

The navigator is fully generic (JSON tree in, slices out); this registry is the
ONE place that carries each result type's meaning. The agent's system prompt
includes the legend so it can interpret the otherwise-opaque tree.

Adding a new doc type = add one entry here. No navigator/agent changes.
"""

from __future__ import annotations

SCOUT_LEGEND = """This is a SCOUT result: a document's product targets or plan commitments tested against external web/literature/registry evidence. Shape:
- variables[]: the units analyzed (name, description, and originating block_ids for document-extracted units).
- search_plan[]: every lane-native retrieval request, the exact intent_ids/input_queries compiled into it, its coverage tracks, originating document block_ids, finding_count, and all retrieved source_urls (including sources that produced no accepted insight).
- development_landscape[]: deterministic groups of explicitly named programs from structured trial, compound, and regulatory records. Sponsor, phase, and status are shown only when a source supplied them; supporting_findings retain the citations.
- safety_signals[]: structured official warnings, recalls, and surveillance reports for document-stated products. FAERS counts are report counts, not incidence, and FAERS/MAUDE records do not establish causation; read each qualification and cite its supporting_findings.
- matches[]: each is one external-evidence insight + its relation to the document:
    contradicts = evidence shows the target is disproven/unachievable, or a stated fact is wrong;
    extends = adds info / the current standard differs from an aspirational target (a gap, not a failure);
    confirms = supports the target; unrelated = off-topic. Each insight has a stable id and exact supporting_findings; each match has the document block_ids it compares against.
- conformity[]: per quantitative target, an exact block-cited document bound is calibrated against complete source-quoted measurements. Targets and measurements share one NumericExpression plus the same seven-slot semantic profile; explicit unknown/other states are not guesses. measurements[] contains only AI-normalized comparable atomic scalars whose exact quote, value, operator, unit, URL, source identity, and field ownership passed deterministic validation. excluded_measurements[] retains complete contextual, incompatible, uncertain, or duplicate measurements and their reasons; source_dispositions[] records sources with no relevant measurement or an unresolved mapping. Benchmark minimum/maximum/mean/median/quartiles/standard deviation and target/ambition percentiles describe this selected cohort only. target_meeting_count/rate is the literal observed share, not a confidence interval or forecast probability. `legacy_unverified` means the imported file predates this provenance contract and requires a rerun.
- precedents[]: two independent axes per variable: precedent coverage (direct/adjacent/none/unknown) and prior outcome (favorable/mixed/unfavorable/unknown), each with its own supporting insight IDs plus document block_ids.
- assessments[]: per variable, weight-of-evidence strength (well_grounded/partial/thin/unsupported/unknown), doc_target, exact document block_ids, and only the supporting_insight_ids/findings actually used.
- stats: funnel counts.
Note: Match relations and Precedent answer DIFFERENT questions and can differ without contradicting each other: relations compare each fact with the document, while precedent asks whether the underlying approach has a track record."""

INSPECTOR_LEGEND = """This is an INSPECTOR result: a document graded inward against its rubric. Shape:
- dimensions: document-level grades (A-F) on completeness (is content present?), adherence (does it follow the rubric's structure/format?), rigor (is the content specific, measurable, sound?).
- section_grades[]: per section - is_present, the three dimension grades (each with issues[] and a recommendation), missing_variables[], and variable_grades[] (per-variable dimension grades).
- cross_section_findings[]: contradictions that span MULTIPLE sections (description, the sections involved, a recommendation).
- top_issues[]: the most severe issues across the document."""

ALIGNER_LEGEND = """This is an ALIGNER result: a traceable comparison between a reference product-development document and a downstream or later comparison document. Shape:
- reference_document and comparison_document identify the two artifacts and their document types.
- units[]: explicit, independently checkable targets, activities, milestones, requirements, dependencies, or risk responses. Every unit retains its exact source block_ids and document role.
- links[]: one traceability relation with reference/comparison unit IDs, exact block IDs, and a concise reason:
    aligned = the substantive commitment was preserved;
    modified = the topic continues but scope, value, timing, population, ownership, or implementation changed;
    conflict = the two statements cannot both hold as written;
    missing = a reference unit has no comparison counterpart;
    introduced = a comparison unit has no reference antecedent.
- stats: deterministic counts of units and relations.
- unit_types[] and relations[]: the exact controlled-vocabulary definitions used for this result.
Aligner does not assess investment risk, grade document quality, or retrieve external evidence. Do not interpret missing as automatically bad; explain it in the context of the two document roles."""

_LEGENDS: dict[str, str] = {
    "aligner": ALIGNER_LEGEND,
    "scout": SCOUT_LEGEND,
    "inspector": INSPECTOR_LEGEND,
}


def legend_for(result_type: str) -> str:
    """Return the semantic legend for a result type, or a neutral fallback."""
    return _LEGENDS.get(
        result_type,
        "This is a structured analysis result. Navigate it as a JSON tree.",
    )
