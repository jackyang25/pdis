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
- development_landscape[]: deterministic groups of structured development records. source_role states the record's explicit study role when the provider supplied one; target_relationship separately states whether the record is direct, analogous, adjacent, unrelated, or unknown relative to the uploaded product. Sponsor, phase, and status appear only when source-supplied; supporting_findings retain the citations.
- safety_observations[]: source-owned official safety information and reported-event surveillance records. record_type and source_system distinguish labels and recalls from FAERS and MAUDE observations. target_relationship distinguishes direct observations from analogous or adjacent context; never attribute contextual observations to the uploaded product. source_role remains a separate provider-supplied study axis. FAERS report_count values are report counts, not incidence, and FAERS/MAUDE observations do not establish causation; read each qualification and cite its supporting_findings.
- matches[]: each is one external-evidence insight + its relation to the document:
    contradicts = evidence shows the target is disproven/unachievable, or a stated fact is wrong;
    extends = adds info / the current standard differs from an aspirational target (a gap, not a failure);
    confirms = supports the target; unrelated = off-topic. Each insight has a stable id and exact supporting_findings; each match has the document block_ids it compares against.
- conformity[]: per quantitative target, an exact block-cited document bound is calibrated against complete source-quoted measurements. Targets and measurements share one NumericExpression plus the same eight-slot semantic profile (measure, endpoint, intervention, population, regimen, time horizon, statistic, conditions); every specified target slot has exact document provenance, and explicit unknown/other states are not guesses. measurements[] contains only AI-normalized comparable atomic scalars whose exact quote, value, operator, unit, URL, source identity, and field ownership passed deterministic validation. excluded_measurements[] retains complete contextual, incompatible, uncertain, or duplicate measurements and their reasons; source_dispositions[] records every source passage considered: the model's verdict (measurements_found, no_relevant_measurement, uncertain) or not_assessed, which means this run obtained no verdict and names the reason in failure_code. not_assessed is a processing gap, never a statement about the evidence. Benchmark minimum/maximum/mean/median/quartiles/standard deviation and target/ambition percentiles describe this selected cohort only. target_meeting_count/rate is the literal observed share, not a confidence interval or forecast probability.
- precedents[]: two independent axes per variable: precedent coverage (direct/adjacent/none/unknown) and prior outcome (favorable/mixed/unfavorable/unknown), each with its own supporting insight IDs plus document block_ids.
- assessments[]: per variable, weight-of-evidence strength (well_grounded/partial/thin/unsupported/unknown), doc_target, exact document block_ids, and only the supporting_insight_ids/findings actually used.
- stats: funnel counts.
Note: Match relations and Precedent answer DIFFERENT questions and can differ without contradicting each other: relations compare each fact with the document, while precedent asks whether the underlying approach has a track record."""

INSPECTOR_LEGEND = """This is an INSPECTOR result: a document assessed inward against its rubric. Shape:
- each dimension verdict is one of critical | for_consideration | meets | not_applicable, on completeness (is content present?), adherence (does it follow the rubric's structure/format?), rigor (is the content specific, measurable, sound?). There is no letter grade and no overall score.
- gap_counts: how many critical and for_consideration gaps were found. Present on the document and on each section, derived from the verdicts beneath it. A section that has variables carries no verdict of its own; its variables do.
- section_grades[]: per section - is_present, dimensions (used for a section with no variables), variable_grades[], gap_counts, and mapped_block_ids[] (the blocks assigned to that section; an assignment, not a citation).
- each dimension verdict carries issues[], a recommendation, and cited_block_ids[] - the blocks THAT judgment cited. The three dimensions judge and cite independently, so do not treat one dimension's lineage as another's.
- each variable_grade carries content_status: substantive | partial | placeholder | missing | not_applicable. This is the authority on presence: 'missing' means the document does not contain it and it therefore cites no block, while 'placeholder' means a token like <<TBD>> is present. There is no separate list of missing names.
- cross_section_findings[]: contradictions that span MULTIPLE sections (description, the sections involved, a recommendation).
- top_issues[]: the most severe issues across the document, each keeping its section, variable, dimension, severity, recommendation, and cited blocks as separate fields. An absent section or variable outranks any assessed gap."""

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
Aligner does not assess investment risk, judge document quality, or retrieve external evidence. Do not interpret missing as automatically bad; explain it in the context of the two document roles."""

WORKSPACE_LEGEND = """This is a read-only PDIS WORKSPACE bundle. Shape:
- catalog[]: every available or planned tool with its audience, workflow, availability, delivery, and provider labels. Catalog entries describe capabilities; they are not analysis findings.
- results[]: current client-held final analyses or direct utility outputs. Each entry has a stable id, result_type, human-readable label, analysis tree, and the exact document_block_ids available to it.
- conversation_attachments[]: transient files the user added to this conversation. They are user-supplied context, not PDIS findings or independently verified evidence; their block_ids link to the same exact document-reading tools.
- An absent result type means that no eligible current result of that type is available. Say so plainly; never imply that a tool was run.
Use each entry's result_type to interpret its analysis: Inspector assesses one document against a rubric; Aligner traces commitments across two documents; Scout tests document targets against external evidence and precedent; Chunker exposes parsed source blocks; Searcher contains direct normalized retrieval findings. Compare entries only when the question calls for it, and identify which result supports each statement."""

_LEGENDS: dict[str, str] = {
    "aligner": ALIGNER_LEGEND,
    "scout": SCOUT_LEGEND,
    "inspector": INSPECTOR_LEGEND,
    "workspace": WORKSPACE_LEGEND,
}


def legend_for(result_type: str) -> str:
    """Return the semantic legend for a result type, or a neutral fallback."""
    return _LEGENDS.get(
        result_type,
        "This is a structured analysis result. Navigate it as a JSON tree.",
    )
