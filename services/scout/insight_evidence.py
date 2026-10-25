"""How retrieved evidence is shown to the stages that judge it.

Drift, grounding and precedent each decide something about a variable's insights, and
their rubrics weigh what only the sources can show: whether a finding is recent enough
to settle a claim about the present, whether it is a trial registry, a regulator or a
press release, whether its excerpt is the source's words or a search engine's sentence
about it. They were shown the insight's paraphrase and a list of URLs, so every one of
those judgements was made about a sentence a model had already written.

One renderer, because the three judge the same insights and must see the same evidence:
a stage shown dates while another is not would disagree with it for a reason no reader
could see. Each supporting record is named by its title, its lane and evidence class,
its publication date at the precision the source stated, what kind of excerpt it carries
and the excerpt's opening, verbatim.
"""

from __future__ import annotations

import copy
from typing import Iterable

from services.searcher import Finding, dedupe_findings, lane_class, published_label

from .context import limit_document_context
from .models import Insight

#: How much of each supporting record's excerpt a verdict stage sees.
#:
#: The opening of the source's own text, not all of it, because the verdict stages read
#: every insight of a variable in one request and a variable can hold dozens: an
#: insight already states the fact its extraction read out of the whole excerpt, and
#: what the verdict needs beside it - who ran the study, its design, its population - is
#: what an abstract or a registry record states first. Searcher still owns the excerpt
#: itself; this bounds only what a judging prompt repeats of it.
VERDICT_EXCERPT_CHARS = 700

#: What a reader of the excerpt is reading, by `Finding.excerpt_kind`.
EXCERPT_KIND_LABELS = {
    "passage": "the source's own text",
    "structured_fields": "the source's record fields, labelled by the search tool",
    "generated": "a search engine's summary of the page, not the source's own words",
}


def render_finding(finding: Finding) -> str:
    """One supporting record: what it is, when it is from, and how it opens."""
    lane = finding.source
    label = finding.source_labels.get(lane, lane)
    lines = [
        f"    - {finding.title or finding.url}",
        f"      source: {label} ({lane_class(lane)} evidence) | published: "
        f"{published_label(finding.published_at and finding.published_at.date(), finding.published_precision)} | {finding.url}",
    ]
    excerpt = " ".join((finding.excerpt or "").split())
    if excerpt:
        opening = excerpt[:VERDICT_EXCERPT_CHARS]
        if len(excerpt) > VERDICT_EXCERPT_CHARS:
            opening = opening.rsplit(" ", 1)[0] + " [...]"
        kind = EXCERPT_KIND_LABELS.get(finding.excerpt_kind, finding.excerpt_kind)
        lines.append(f"      excerpt ({kind}): {opening}")
    else:
        lines.append("      excerpt: none was retrieved")
    return "\n".join(lines)


def render_insight_evidence(insight: Insight, *, label: str) -> str:
    """One insight with every record it rests on. ``label`` is how the stage cites it."""
    lines = [f"{label} {insight.statement}"]
    if insight.query_tracks:
        lines.append(f"    discovery tracks: {', '.join(insight.query_tracks)}")
    lines.append("    supporting records:")
    lines.extend(render_finding(finding) for finding in insight.supporting_findings)
    return "\n".join(lines)


def render_insights(insights: list[Insight]) -> str:
    """A variable's insights, numbered from 0 for stages that cite them by index."""
    return "\n\n".join(
        render_insight_evidence(insight, label=f"[{index}]")
        for index, insight in enumerate(insights)
    ) or "(none)"


def selected_insights(raw: object, insights: list[Insight]) -> list[Insight]:
    """The insights a reply cited by index, in its order, each once."""
    indices = dict.fromkeys(
        item
        for item in (raw if isinstance(raw, list) else [])
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item < len(insights)
    )
    return [insights[index] for index in indices]


def supporting_findings(insights: Iterable[Insight]) -> list[Finding]:
    """The records behind a set of insights, one entry per record.

    Copies, because merging two retrievals of one record rewrites the entry it keeps,
    and the insight's own records must stay as retrieved.
    """
    return dedupe_findings(
        copy.copy(finding) for insight in insights for finding in insight.supporting_findings
    )


def binding_message(binding: str) -> str:
    """A variable's canonical binding: the prefix every verdict request about it shares."""
    return (
        "Canonical document binding (authoritative; do not reinterpret):\n"
        + (limit_document_context(binding) or "(no document binding)")
    )


def insights_message(insights: list[Insight], instruction: str) -> str:
    """A variable's insights and their records, sent after the binding and its images."""
    return (
        "\n\nExternal-evidence insights for this variable, each with the records it "
        "rests on:\n" + render_insights(insights) + f"\n\n{instruction}"
    )
