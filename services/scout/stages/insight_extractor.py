"""Stage 2: extract atomic Insights from external retrieval Findings.

Given one variable's batch of Findings, the LLM extracts atomic factual statements,
each citing one or more of them by record. Code re-attaches the full Finding objects
and the coverage tracks and targets of the requests that retrieved them. Which
statements are one fact is decided afterwards, by `insight_reconciler`, and nowhere
here.
"""

from __future__ import annotations

from services.searcher import Finding
from shared.ai import Effort, ModelTask

from ..ai import request_validated
from ..ai_contracts import insight_batch
from ..lineage import RetrievalLineage
from ..models import Insight, LLMClientProtocol

#: The fast tier at low effort: extraction states what the sources say; the stages that
#: weigh it run after, and see the records it cites.
TASK: ModelTask = "fast"
EFFORT: Effort = "low"
DEFAULT_MAX_TOKENS = 24000


def extract_insights(
    findings: list[Finding],
    llm_client: LLMClientProtocol,
    *,
    indication: str,
    intervention_class: str,
    attribute_ref: str,
    attribute_description: str = "",
    lineage: RetrievalLineage | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Insight]:
    """Return Insights extracted from the supplied Findings of one variable."""
    if not findings:
        return []
    lineage = lineage or RetrievalLineage(())
    findings_by_key = {finding.record_key: finding for finding in findings}
    if len(findings_by_key) != len(findings):
        raise ValueError("an insight batch holds one entry per record")

    # A batch that never returns a valid answer raises rather than returning no insights,
    # which would read exactly like findings that said nothing about this variable. The
    # pipeline records the field not assessed (`UnreadField`) and the run goes on.
    parsed = request_validated(
        llm_client,
        insight_batch(list(findings_by_key)),
        build_system_prompt(
            indication=indication,
            intervention_class=intervention_class,
            attribute_ref=attribute_ref,
            attribute_description=attribute_description,
        ),
        _user_message(findings, attribute_ref=attribute_ref, lineage=lineage),
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
        parse=lambda payload: _validated_insights(payload, set(findings_by_key)),
        failure=f"Insight extraction failed for {attribute_ref}",
    )

    insights: list[Insight] = []
    for item in parsed:
        supporting = [
            findings_by_key[key] for key in dict.fromkeys(item["supporting_record_keys"])
        ]
        insights.append(
            Insight(
                statement=item["statement"].strip(),
                supporting_findings=supporting,
                # The first supporting finding's query: the best single attribution.
                query=supporting[0].query,
                query_tracks=lineage.tracks(attribute_ref, supporting),
                retrieval_target_ids=lineage.target_ids(attribute_ref, supporting),
                attribute_ref=attribute_ref,
            )
        )
    return insights


def build_system_prompt(
    *,
    indication: str,
    intervention_class: str,
    attribute_ref: str | None,
    attribute_description: str,
) -> str:
    return (
        f"You extract atomic factual insights from external search findings about "
        f"a {intervention_class} for {indication}.\n\n"
        "You are extracting insights for ONE specific variable:\n"
        f"Variable: {attribute_ref or 'unknown'}\n"
        f"Definition: {attribute_description or 'No definition provided.'}\n\n"
        "Relevance rule:\n"
        "- Extract ONLY facts that are genuinely about THIS variable's topic, as defined above.\n"
        "- If a finding is about a DIFFERENT topic, SKIP it - do not extract it. "
        "Examples of skips: an identity fact like \"X is a malaria vaccine\" when "
        "the variable is about price; a general dosing-schedule recommendation when "
        "the variable is about a companion diagnostic.\n"
        "- Returning an EMPTY list is correct and expected when the findings contain "
        "nothing about this variable's topic. Do NOT stretch loosely-related facts to "
        "fill the field.\n"
        "- Keep facts that are clearly on-topic OR closely related to the variable's "
        "definition. When genuinely unsure whether a fact fits, prefer keeping it over "
        "dropping it (favor recall slightly, to avoid emptying fields that have real content).\n\n"
        "Rules:\n"
        "- Each Insight is ONE atomic factual statement (one fact, not a paragraph).\n"
        "- Every Insight must cite at least one supporting Finding by its record key.\n"
        "- Write every Insight statement in English, even when the supporting Finding "
        "is in another language. Preserve the original source via its URL/title.\n"
        "- Prefer recent, source-attributable facts (regulatory actions, trial readouts, "
        "approvals, safety signals). Skip opinion and marketing language.\n"
        "- Extract only SUBSTANTIVE facts: approvals, recommendations, trial readouts, "
        "efficacy/safety findings, regulatory actions, new products, epidemiology shifts. "
        "Do NOT extract meta-statements that merely note a resource exists - e.g. "
        "\"X published a Q&A page\", \"a webpage describes Y\", \"a fact sheet is available\". "
        "Those are not insights. Extract the underlying fact only if the source states one.\n"
        "- Search silence is not a source-owned fact. Do not emit statements that the "
        "retrieved findings lack, omit, or fail to confirm something, or generalize "
        "silence in this batch to the wider evidence base. If no source states a relevant "
        "fact, return an empty insights array. Query wording is discovery context, not "
        "evidence that a returned snippet concerns the named subject.\n"
        "- Preserve explicit source-owned negative findings, such as a regulator reporting "
        "non-approval or a study reporting no observed effect. Keep the source's subject, "
        "time, and scope; do not strengthen an absence of demonstrated effect into proof "
        "that no effect is possible. When a finding mixes a substantive fact with search "
        "commentary, extract only the substantive fact.\n"
        "- Preserve claim ownership. A value mentioned as background from a prior study, "
        "product, guideline, or publication is NOT a result of the current source record. "
        "If retained, the statement must explicitly attribute it to that prior evidence. "
        "Never rewrite background as a result of the page, paper, or registry record that "
        "mentions it. Skip the fact when ownership remains ambiguous.\n"
        "- Registry protocols and planned outcomes describe what a study intends to measure; "
        "they are not observed results. State them as planned only when that planning fact is "
        "itself relevant to this variable.\n"
        "- Do not invent facts not present in the findings.\n\n"
        "Return only the schema-bound `insights` response."
    )


def _user_message(
    findings: list[Finding],
    *,
    attribute_ref: str,
    lineage: RetrievalLineage,
) -> str:
    lines = ["Findings, each headed by the record key to cite it by:"]
    for finding in findings:
        lines.append(f"\n--- record {finding.record_key} ---")
        lines.append(f"url: {finding.url}")
        lines.append(f"title: {finding.title}")
        lines.append(f"source lane: {finding.source}")
        if finding.published_at:
            lines.append(f"published: {finding.published_at.isoformat()}")
        queries = finding.queries or [finding.query]
        lines.append(f"discovered by: {' | '.join(query for query in queries if query)}")
        tracks = lineage.tracks(attribute_ref, [finding])
        if tracks:
            lines.append(f"coverage tracks: {', '.join(tracks)}")
        if finding.excerpt:
            lines.append(f"excerpt: {finding.excerpt}")
    lines.append("\nExtract insights now.")
    return "\n".join(lines)


def _validated_insights(parsed: object, known_keys: set[str]) -> list[dict]:
    """Every item states a fact and cites records from this request, or none is used."""
    if not isinstance(parsed, list):
        raise ValueError("no insights array was returned")
    for item in parsed:
        keys = item.get("supporting_record_keys") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or not str(item.get("statement", "")).strip()
            or not isinstance(keys, list)
            or not keys
            or not set(keys) <= known_keys
        ):
            raise ValueError(
                "every insight needs a statement and at least one supporting record "
                "key from this request"
            )
    return parsed
