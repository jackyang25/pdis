"""An alignment as export tables: one per comparison, in the order the run made them.

Each requirement the reference document sets, its verdict, and what the document measured
against it says, grouped by verdict in the page's reading order - shortfalls first. Both
citation lists are kept and named by document, because which document a passage is in is
the difference between the bar and the answer to it.

The page's chain warnings are not here. They are derived when the page is read, from the
two comparisons' shared passages, and restating that derivation on the server would be a
second implementation of it.
"""

from __future__ import annotations

from typing import Any

from shared.vocabulary import display_label
from shared.report_export import ExportReport, Table, count_summary, passage_sources

#: `VERDICT_LABELS` in the web's `lib/api.ts`, in the page's `VERDICT_ORDER`.
VERDICT_LABEL = {
    "falls_short": "Falls short",
    "not_comparable": "Not comparable",
    "not_addressed": "Not addressed",
    "exceeds": "Exceeds",
    "meets": "Meets",
}
ORDER = tuple(VERDICT_LABEL)


def export_report(alignment: dict[str, Any]) -> ExportReport:
    blocks = {block["id"]: block for block in alignment.get("blocks") or []}
    documents = {document["doc_id"]: document for document in alignment["documents"]}
    tables = []
    for edge in alignment["edges"]:
        reference = documents[edge["reference_doc_id"]]["display_name"]
        comparison = documents[edge["comparison_doc_id"]]["display_name"]
        measured = display_label(documents[edge["comparison_doc_id"]]["source_type"])
        findings = [finding for finding in alignment["findings"] if finding["edge_id"] == edge["edge_id"]]
        findings.sort(key=lambda finding: ORDER.index(finding["verdict"]))
        rows = [
            (
                finding["requirement"],
                VERDICT_LABEL[finding["verdict"]],
                finding["statement"],
                passage_sources(
                    [*_blocks(finding["reference_spans"]), *finding["reference_visual_block_ids"],
                     *_blocks(finding["comparison_spans"]), *finding["comparison_visual_block_ids"]],
                    blocks, name_documents=True,
                ),
            )
            for finding in findings
        ]
        counts = ((sum(finding["verdict"] == verdict for finding in findings), VERDICT_LABEL[verdict]) for verdict in ORDER)
        tables.append(Table(
            heading=f"{reference} → {comparison}",
            note=f"{edge['question']} {count_summary(len(findings), ('requirement', 'requirements'), counts)}",
            columns=("Requirement", "Verdict", f"What the {measured} says", "Sources"),
            rows=rows,
            widths=(4, 1.3, 4, 3),
        ))
    return ExportReport(
        title="Alignment: " + " · ".join(display_label(document["source_type"]) for document in alignment["documents"]),
        context=f"{display_label(alignment['indication'])} · {display_label(alignment['intervention_class'])}",
        about=(
            "PDIS Aligner read each requirement a reference document sets and judged how the "
            "document measured against it meets it."
        ),
        tables=tables,
    )


def _blocks(spans: list[dict[str, Any]]) -> list[str]:
    return [block_id for span in spans for block_id in span["block_ids"]]
