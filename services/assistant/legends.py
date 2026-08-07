"""Per-result-type semantic legends for the Ask assistant.

The navigator is fully generic (JSON tree in, slices out); this registry is the
ONE place that carries each result type's meaning. The agent's system prompt
includes the legend so it can interpret the otherwise-opaque tree.

Adding a new doc type = add one entry here. No navigator/agent changes.
"""

from __future__ import annotations

SCOUT_LEGEND = """This is a SCOUT result: a document's product targets or plan commitments tested against external web/literature/registry evidence. Shape:
- variables[]: the units analyzed (name, description, and originating block_ids for document-extracted units).
- search_plan[]: every lane-native retrieval request, the exact intent_ids/input_queries compiled into it, its coverage tracks, originating document block_ids, finding_count, and all retrieved source_urls (including sources that produced no accepted insight). excluded_before_window[] is a subset of those URLs that the run retrieved and then held out because the source dated them before published_since; they informed no insight, precedent, or statistic. Cite them only as what the window excluded, never as evidence, and note that only their URLs were retained. A source that supplied no date is never excluded.
- published_since: the ISO date this run scoped retrieval to, or empty for no window. When set, every count, benchmark, and precedent below describes only evidence published on or after it, so say so when reporting them.
- development_landscape[]: deterministic groups of structured development records. source_role states the record's explicit study role when the provider supplied one; target_relationship separately states whether the record is direct, analogous, adjacent, unrelated, or unknown relative to the uploaded product. Sponsor, phase, and status appear only when source-supplied; supporting_findings retain the citations.
- safety_observations[]: source-owned official safety information and reported-event surveillance records. record_type and source_system distinguish labels and recalls from FAERS and MAUDE observations. target_relationship distinguishes direct observations from analogous or adjacent context; never attribute contextual observations to the uploaded product. source_role remains a separate provider-supplied study axis. FAERS report_count values are report counts, not incidence, and FAERS/MAUDE observations do not establish causation; read each qualification and cite its supporting_findings.
- matches[]: each is one external-evidence insight + its relation to the document:
    contradicts = evidence shows the target is disproven/unachievable, the same candidate or configuration failed, or a stated fact is wrong. Evidence about a different population, comparator, or setting does NOT contradict; it concerns something else;
    extends = adds info / the current standard differs from an aspirational target (a gap, not a failure);
    confirms = supports the target, even when it also adds new facts; unrelated = off-topic for this claim. Note `unrelated` here is a relation to a CLAIM; `target_relationship.unrelated` on a development or safety record is a different axis meaning the record concerns no comparable product. Each insight has a stable id and exact supporting_findings; each match has the document block_ids it compares against.
- conformity[]: per quantitative target, an exact block-cited document bound is calibrated against complete source-quoted measurements. Targets and measurements share one NumericExpression plus the same eight-slot semantic profile (measure, endpoint, intervention, population, regimen, time horizon, statistic, conditions); every specified target slot has exact document provenance, and explicit unknown/other states are not guesses. measurements[] contains only AI-normalized comparable atomic scalars whose exact quote, value, operator, unit, URL, source identity, and field ownership passed deterministic validation. excluded_measurements[] retains complete contextual, incompatible, uncertain, or duplicate measurements and their reasons; source_dispositions[] records every source passage considered: the model's verdict (measurements_found, no_relevant_measurement, uncertain) or not_assessed, which means this run obtained no verdict and names the reason in failure_code. not_assessed is a processing gap, never a statement about the evidence. Benchmark minimum/maximum/mean/median/quartiles/standard deviation and target/ambition percentiles describe this selected cohort only. target_meeting_count/rate is the literal observed share, not a confidence interval or forecast probability.
- precedents[]: two independent axes per variable: precedent coverage (direct/adjacent/none/unknown) and prior outcome (favorable/mixed/unfavorable/unknown), each with its own supporting insight IDs plus document block_ids.
- assessments[]: per variable, weight-of-evidence strength (well_grounded/partial/thin/unsupported/unknown), doc_target, exact document block_ids, and only the supporting_insight_ids/findings actually used.
- stats: funnel counts.
Note: Match relations and Precedent answer DIFFERENT questions and can differ without contradicting each other: relations compare each fact with the document, while precedent asks whether the underlying approach has a track record."""

INSPECTOR_LEGEND = """This is an INSPECTOR result: a document assessed inward against its rubric. Shape:
- sections[]: every rubric section, in the order the rubric author wrote them. Each has is_present, mapped_block_ids[] (the blocks assigned to it - a deterministic parse assignment, NOT a citation, so never present it as evidence), units[], and status_counts.
- sections[].units[]: one unit per thing the rubric asks about. A section with no variables contributes exactly one unit whose variable_name is null; a section with variables contributes one unit per variable. The rubric owns how many units exist, so a unit the model said nothing about still appears - the denominator is identical for every document on this rubric and cannot shrink.
- each unit's status is met | could_be_stronger | not_met | not_applicable, derived from the findings on that unit alone: met means exactly zero findings. not_applicable means the rubric itself marks the unit optional and the document does not supply it, so it is NOT a shortfall. There is no letter grade, no severity scale, and no overall score.
- units[].findings[]: one finding is one thing to fix - exactly one statement, one recommendation, one reason, and the block IDs that finding was read from. A unit with three problems has three findings, at most one per reason, so a count of findings is a count of fixable items.
- reason is one of: missing (nothing is there), placeholder (a token such as <<TBD>> sits where the value belongs), unmet (content is present and does not satisfy the requirement), off_template (structure or naming deviates), unclear (satisfies the requirement but is vague or unmeasurable), conflicting (two sections disagree). level is derived from reason: missing, placeholder, unmet, and conflicting are not_met; off_template and unclear are could_be_stronger.
- cited_block_ids is empty exactly when reason is missing, because absence cites nothing. Every other finding cites the passage it was read from, so it can be checked against the document.
- rank orders every finding across the whole document: sort by rank to get "what to fix first". Do not re-rank. The order is level, then the rubric author's own section and variable sequence - there is no weighting to apply.
- document_findings[]: conflicts spanning sections, which no single unit owns. reason is always conflicting and both names are null; the sections involved are read back from cited_block_ids against sections[].mapped_block_ids.
- consistency_status and assessment_status describe whether the run completed. They are process facts, never findings: a failed check means the document was not checked, which is not the same as a document with nothing wrong."""


ALIGNER_LEGEND = """This is an ALIGNER result. Aligner is between designs: its comparison analysis was removed and a run currently parses the documents without comparing them. Shape:
- documents[]: every artifact in the run, each with its doc_id and source_type (itpp, ctpp, ipdp, and any other type configured). A run holds two or more; do not assume two.
- edges[]: the comparisons this run WOULD make, each naming a reference_doc_id, a comparison_doc_id, and the question it asks. reference is the document being honoured and comparison is the one measured against it - the direction is meaningful, not a diff order. An edge is a declared intent, NOT a finding: no comparison has been performed.
- blocks[]: every parsed block from every document, readable through the same document tools as any other result.
There are no units, links, relations, counts, or findings of any kind. If the user asks what changed, what drifted, or whether one document satisfies another, say plainly that Aligner does not currently report that - do not derive it yourself from the blocks, and do not read an edge as evidence that a comparison was made.
Aligner never judges document quality (Inspector does that against a rubric) and never retrieves external evidence (Scout does that)."""

WORKSPACE_LEGEND = """This is a read-only PDIS WORKSPACE bundle. Shape:
- catalog[]: every available or planned tool with its audience, workflow, availability, delivery, and provider labels. Catalog entries describe capabilities; they are not analysis findings. Each description names what a tool reads and the authority it is judged against, which is what tells them apart; a tool whose description names no authority renders no verdict and only reports what a source already says.
- results[]: current client-held final analyses or direct utility outputs. Each entry has a stable id, result_type, human-readable label, analysis tree, and the exact document_block_ids available to it.
- conversation_attachments[]: transient files the user added to this conversation. They are user-supplied context, not PDIS findings or independently verified evidence; their block_ids link to the same exact document-reading tools.
- An absent result type means that no eligible current result of that type is available. Say so plainly; never imply that a tool was run.
Use each entry's result_type to interpret its analysis: Inspector judges one document against a rubric; Aligner judges the iTPP, cTPP, and IPDP against each other; Scout judges one document's targets against external evidence and precedent; Chunker exposes parsed source blocks; Searcher contains direct normalized retrieval findings. Compare entries only when the question calls for it, and identify which result supports each statement."""

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
