"""A final evidence review as Word tables: one row per searched field, then the numeric targets.

Each field keeps its grounding and its precedent with the reason the model gave, and the
records the grounding cites, so the row carries what its verdict rests on. The numbers are the
calibration's descriptive figures over the measurements admitted at review, said to be that,
because lifted out of the page a range and a median are easily read as a confidence interval.

Only a final result exports. A review checkpoint is still being decided, and a file of it would
read as the answer.
"""

from __future__ import annotations

from typing import Any

import re

from shared.vocabulary import attribute_label, display_label
from shared.word_export import Table, WordReport, count_summary, document_name, word_document

#: `GROUNDING_LABEL`, `PRECEDENT_LABEL`, `OUTCOME_LABEL` and `CALIBRATION_BASIS_LABEL` in the
#: web's `lib/scout-labels.ts`.
GROUNDING_LABEL = {
    "well_grounded": "Well grounded",
    "partial": "Partly grounded",
    "thin": "Thinly grounded",
    "unsupported": "Unsupported",
    "unknown": "Grounding unknown",
    "no_evidence": "No evidence to ground",
    "not_searched": "Not searched",
    "not_assessed": "Grounding not assessed",
}
PRECEDENT_LABEL = {
    "direct": "Direct precedent",
    "adjacent": "Adjacent precedent",
    "none": "No precedent found",
    "unknown": "Precedent unknown",
    "no_evidence": "No evidence on precedent",
    "not_searched": "Not searched",
    "not_assessed": "Precedent not assessed",
}
OUTCOME_LABEL = {
    "favorable": "Favorable outcome",
    "mixed": "Mixed outcome",
    "unfavorable": "Unfavorable outcome",
    "unknown": "Outcome unknown",
}
CALIBRATION_LABEL = {"insufficient": "Too few", "limited": "Limited", "sufficient": "Verified"}
#: The states only code records, worded as `verdictNote` on the web words them.
CODE_NOTE = {
    "no_evidence": "Nothing this run retrieved bore on this field, so there was no evidence to judge.",
    "not_searched": "Excluded at review, so Scout did not search for evidence on this field.",
    "not_assessed": "No verdict was obtained for this field. Run the analysis again to retry it.",
}


def export_docx(result: dict[str, Any]) -> bytes:
    if result["phase"] != "final":
        raise ValueError("Only a final Scout result exports; finish the review first.")
    precedents = {signal["attribute_ref"]: signal for signal in result["precedents"]}
    spans = {variable["name"]: variable.get("document_spans") or [] for variable in result["variables"]}
    blocks = {block["id"]: block for block in result.get("blocks") or []}
    assessments = result["assessments"]
    doc_ids = list(dict.fromkeys(block["doc_id"] for block in result.get("blocks") or []))
    tables = [Table(
        heading="Fields",
        note="Each field the run searched: how well external evidence grounds its target, and what precedent shows.",
        columns=("Field", "Document target", "Evidence", "Precedent", "Sources"),
        widths=(1.5, 3, 3.5, 3, 3.5),
        rows=[
            (
                attribute_label(assessment["attribute_ref"]),
                _target(spans.get(assessment["attribute_ref"], []), blocks) or assessment["doc_target"],
                _verdict(GROUNDING_LABEL[assessment["strength"]], assessment["strength"], assessment["reason"]),
                _precedent(precedents.get(assessment["attribute_ref"])),
                _sources(assessment["supporting_findings"]),
            )
            for assessment in assessments
        ],
    )]
    if result["conformity"]:
        tables.append(Table(
            heading="Numeric targets",
            note=(
                "Each target against the comparable measurements admitted at review. Descriptive "
                "figures over those measurements: not confidence intervals, probabilities or forecasts."
            ),
            columns=("Target", "Comparable measurements", "Range", "Median", "Basis"),
            widths=(4, 1.5, 2, 1.5, 1.5),
            rows=[_calibration(score) for score in result["conformity"]],
        ))
    return word_document(WordReport(
        title="Evidence review: " + (", ".join(map(document_name, doc_ids)) or "Scout result"),
        context=" · ".join(display_label(result[key]) for key in ("indication", "intervention_class", "source_type")),
        about=(
            "PDIS Scout searched external evidence for each target the document states and judged "
            "how well it holds up against comparable measurements and development precedent."
        ),
        summary=count_summary(len(assessments), ("field", "fields"), (
            (sum(assessment["strength"] == strength for assessment in assessments), label)
            for strength, label in GROUNDING_LABEL.items()
            if strength in {"well_grounded", "partial", "thin", "unsupported", "unknown"}
            or any(assessment["strength"] == strength for assessment in assessments)
        )),
        notes=[f"Evidence published since {result['published_since']}."] if result.get("published_since") else [],
        tables=tables,
    ))


def _target(spans: list[dict[str, Any]], blocks: dict[str, dict[str, Any]]) -> str:
    """The document's target, a whole table row as one "Heading: value" line per cell.

    The heading is its own title line: a template heading is a title over a line of guidance,
    and the row's text repeats both before every value. Read from the cells the parser
    recorded, never from the span's wording; any other span is the document's words as quoted.
    """
    def collapse(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    lines = []
    for span in spans:
        block = blocks.get(span["block_ids"][0]) if len(span["block_ids"]) == 1 else None
        cells = (block or {}).get("structural_meta", {}).get("table_cells") or []
        if block and cells and collapse(block["content"]) == collapse(span["quote"]):
            lines += [
                f"{next((line.strip() for line in cell['header'].splitlines() if line.strip()), '')}: {cell['value'].strip()}"
                for cell in cells
            ]
        else:
            lines.append(span["quote"].strip())
    return "\n".join(lines)


def _verdict(label: str, state: str, reason: str) -> str:
    """The verdict, then why: the model's reason, or the interface's words for a state only code records."""
    because = CODE_NOTE.get(state) or reason
    return f"{label}\n{because}" if because else label


def _precedent(signal: dict[str, Any] | None) -> str:
    if signal is None:
        return ""
    label = PRECEDENT_LABEL[signal["precedent"]]
    # One classification sets both axes; when code recorded them, the pair says one fact twice.
    if signal["precedent"] not in CODE_NOTE:
        label = f"{label} · {OUTCOME_LABEL[signal['outcome']]}"
    return _verdict(label, signal["precedent"], signal["reason"])


def _sources(findings: list[dict[str, Any]]) -> str:
    lines = []
    for finding in findings:
        label = (finding.get("source_labels") or {}).get(finding["source"], finding["source"])
        about = ", ".join(filter(None, (label, (finding.get("published_at") or "")[:4])))
        lines.append(f"{finding['title']} ({about}) {finding['url']}".strip())
    return "\n".join(dict.fromkeys(lines))


def _number(value: float | None, unit: str) -> str:
    return "" if value is None else f"{value:g}{' ' + unit if unit else ''}"


def _calibration(score: dict[str, Any]) -> tuple[str, ...]:
    target = f"{score['target_label'] or score['target_quote']}: {score['comparator']} {_number(score['target_value'], score['unit'])}"
    count = score["benchmark_count"]
    lowest, highest = score["benchmark_minimum"], score["benchmark_maximum"]
    spread = f"{_number(lowest, '')}–{_number(highest, score['unit'])}" if count and lowest is not None else ""
    return (
        target,
        str(count),
        spread,
        _number(score["benchmark_median"], score["unit"]) if count else "",
        CALIBRATION_LABEL[score["calibration_status"]],
    )
