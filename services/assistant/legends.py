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


ALIGNER_LEGEND = """This is an ALIGNER result: one or more ONE-WAY comparisons between product-development documents. A comparison is not a diff. For each one, the requirements of the reference document are the bar, and the other document is measured against them, requirement by requirement. Shape:
- documents[]: every artifact in the run, each with its doc_id and source_type (itpp, ctpp, ipdp, and any other configured type). A run holds two or more; do not assume two.
- edges[]: the comparisons this run made, each with an edge_id, a reference_doc_id, a comparison_doc_id, and the question it asks. reference sets the requirements and comparison is measured against them. The direction is the substance, not an ordering convention: a document can sit on either side, and with three documents the cTPP is measured against the iTPP and is the reference for the IPDP. Never restate a finding in the opposite direction.
- findings[]: every requirement read out of a reference document, each judged exactly once. This is the denominator as well as the content, so a count taken from it is safe to quote. Each finding carries:
    requirement: the bar, in the reference document's own words, with reference_block_ids citing the passages that state it. Aligner did not decide what matters; it read this out of the document. Compound sentences were split, so one requirement is one fact.
    edge_id: which comparison it belongs to. The same wording under two comparisons is two different questions - a shortfall against an iTPP is about the candidate, one against a cTPP is about the plan - so always name the comparison when reporting a finding.
    verdict: meets | exceeds | falls_short | not_comparable | not_addressed. Closed, and asymmetric on purpose:
        meets = the measured document satisfies the requirement;
        exceeds = it does better than the requirement asks. Worth reporting, because it can mean the bar is stale or the candidate is over-specified. Never fold it into meets;
        falls_short = it addresses the requirement and states less than it asks;
        not_comparable = it addresses the subject but not in terms that can be measured against the requirement - a qualitative claim against a numeric bar, a different population, a different endpoint. This is NOT a claim that the document is worse, and NOT silence. Do not restate it as either;
        not_addressed = the document says nothing on the subject. Say exactly that. It is often a question about which document should carry the requirement rather than a deficiency in this one.
    statement: the model's sentence about what the measured document states, with comparison_block_ids citing the passages it was read from. not_addressed cites nothing, because it is a claim about the absence of text.
    gap: on falls_short and not_comparable only, one sentence naming what is still to close - the shortfall, or what would have to be stated for the two to be comparable. That sentence is the actionable output: it is what a reader takes back to whoever wrote the document. Always quote or paraphrase it when reporting one of these.
- blocks[]: every parsed block from every document, readable through the same document tools as any other result. A finding's two citation lists point into different documents: reference_block_ids into the one that sets the bar, comparison_block_ids into the one being measured. Never present one as the other.
There is no compliance score and no percentage. Do not compute one: a single figure blending "the candidate meets this", "it beats this", "it says something that cannot be compared" and "this document does not cover it" would misrepresent the review. Report the verdicts separately, note that they sum to the total, and do not compare totals across two different comparisons - the total is however many requirements that reference document happens to state.
Aligner never judges document quality (Inspector does that against a rubric) and never retrieves external evidence (Scout does that). If the user asks whether a target is achievable, say that is Scout's question, run separately per document."""

EXPERT_LEGEND = """This is an EXPERT result: one stage gate's SME question bank triaged against a set of product-development documents. Expert does not answer the questions and renders no verdict on the documents - it reports which of them the supplied material answers and which it does not. Shape:
- gate_id / gate_label: the gate this bank belongs to. A different gate asks different questions of the same documents.
- bank_source: the authored SME question bank these questions were transcribed from, named with its version. Cite it when a reader asks where a question comes from or whether it is current, and never present a question as PDIS's own wording.
- documents[]: every document read, by doc_id and source_type. Every applicable question was read against all of them; nothing was withheld because of an assumption about which document ought to hold an answer.
- disciplines[]: the eight owning disciplines, in the order the bank's authors wrote them, each with questions[]. The discipline IS the routing, and it is the only grouping the source document guarantees. Nothing is ranked - the order is the authors' sequence, so two runs on one gate compare line by line. Never re-order or re-rank it.
- disciplines[].questions[]: every question the gate asks, each carrying its full text and exactly one state. The denominator cannot shrink, which is what makes a count safe to quote.
- state is answered | partly_answered | not_found | not_applicable, and only the first three come from a model. They are ordered by how much of the question is closed, because these questions are compound - most ask three to five things in one sentence and are judged clause by clause:
    answered = every part of the question is answered by the supplied material;
    partly_answered = some parts are and some are not. `missing` names exactly what is still not stated, and that sentence is the actionable output: it is what a reader takes back to whoever wrote the document. Always quote or paraphrase `missing` when reporting one of these;
    not_found = it was read against everything supplied and nothing addressed it. Say exactly that. It is NOT a statement about whose fault it is, and NOT a claim that a document ought to have contained it: many of these questions ask about operational facts or matters of judgment that no profile or plan would carry, and the tool cannot tell which is which. When reporting one, name its discipline, because that is who can answer it;
    not_applicable = the question's own text restricts it to another intervention class ("For biologics:"). No model read it. It is NOT a shortfall of any kind.
- missing: on a partly_answered question only, one sentence naming what the question still leaves open. Never present it as the whole question being unanswered, and never invent one for a state that has none.
- source is set only when answered, and it separates an answer that can be checked from one that cannot. document carries cited_block_ids naming the exact passages. context names a transient item the user attached for that one run, in context_label; the file was read into text, used, and discarded, so the label is the entire record and no passage exists to open. NEVER present a context-sourced answer as cited, and when reporting one, say it cannot be verified from this file.
- likely_in[]: where an answer of this kind usually lives, as a HINT. It is not in the source question bank, it played no part in any state, and it may be wrong. Use it only to suggest which document a reader might open or upload next, always hedged. Never say a question "should have been" answered by a document because of it, and never treat it as evidence about the documents supplied.
- context_labels[]: the names of the transient items supplied. Their text is deliberately absent - do not claim to know what they said beyond the statement attributed to them.
- pq marks a WHO prequalification question, transcribed from the source's [PQ] markers. Display only; it affected nothing.
- statement is the model's own sentence about what the material states or what was not found. Questions that are not_applicable carry none, because nothing read them.
There is no coverage score and no weighting. Do not compute one, and do not add partly_answered to answered to imply progress: a single figure blending "the document says it", "it says half of it", and "nobody has asked yet" would misrepresent the review. Report the states separately, and note that they sum to the total."""


WORKSPACE_LEGEND = """This is a read-only PDIS WORKSPACE bundle. Shape:
- catalog[]: every available or planned tool with its audience, workflow, availability, delivery, and provider labels. Catalog entries describe capabilities; they are not analysis findings. Each description names what a tool reads and the authority it is judged against, which is what tells them apart; a tool whose description names no authority renders no verdict and only reports what a source already says.
- results[]: current client-held final analyses or direct utility outputs. Each entry has a stable id, result_type, human-readable label, analysis tree, and the exact document_block_ids available to it.
- results[].priority_item_ids: which findings the tool's own selector chose for its priority panel, in the order shown. IDs only - the findings themselves are in the analysis. This is the list the reader is actually looking at, so use it when a question refers to "the priorities" or to a position in them, and never substitute a list of your own.
- results[].priority_digest: present only when the reader has the priority panel open for that run. It is NOT part of the result and was not produced by the tool's pipeline: `digest` is a passage about the panel's list, and `nominations[]` are items the tool's own selector excluded, each citing document blocks. Treat nominations as things a reader can see on screen that the analysis does not contain - never as findings the tool made, never as evidence, and never as a reason to restate a verdict. When one is relevant, say it was raised alongside the panel rather than by the tool.
- conversation_attachments[]: transient files the user added to this conversation. They are user-supplied context, not PDIS findings or independently verified evidence; their block_ids link to the same exact document-reading tools.
- An absent result type means that no eligible current result of that type is available. Say so plainly; never imply that a tool was run.
Use each entry's result_type to interpret its analysis: Inspector judges one document against a rubric; Aligner judges the iTPP, cTPP, and IPDP against each other; Scout judges one document's targets against external evidence and precedent; Expert triages one stage gate's question bank across a set of documents, reporting only whether the supplied material answers each question; Chunker exposes parsed source blocks; Searcher contains direct normalized retrieval findings. Compare entries only when the question calls for it, and identify which result supports each statement."""

_LEGENDS: dict[str, str] = {
    "aligner": ALIGNER_LEGEND,
    "expert": EXPERT_LEGEND,
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
