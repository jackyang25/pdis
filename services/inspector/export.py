"""A document review as Word tables: one per rubric, in the rubric's own order.

Every requirement keeps its row, sound ones included, so a reader can see what was checked
as well as what needs work; a sound requirement's finding is empty, as on the page. Rubrics
that were not run say why, and the document consistency check states its own outcome,
because "not checked" must never read as "nothing found".
"""

from __future__ import annotations

from typing import Any

from shared.vocabulary import display_label
from shared.word_export import Table, WordReport, count_summary, document_name, passage_sources, word_document

#: `VERDICT_LABEL` in the web's `lib/api.ts`, in the order of `VERDICTS`.
VERDICT_LABEL = {
    "specified": "Specified",
    "not_present": "Not present",
    "placeholder": "Placeholder",
    "insufficient": "Insufficient",
    "vague": "Vague",
    "section_conflict": "Section conflict",
    "not_applicable": "N/A",
}
#: `consistencyDescription` on the web's Inspector page, for the outcomes that limit the check.
CONSISTENCY_NOTE = {
    "partial": "The document exceeded the full-pass context bound; findings reflect the retained section-balanced context.",
    "failed": "The consistency pass did not complete; every section assessment is unaffected. Run the analysis again to retry it.",
    "not_applicable": "Fewer than two mapped sections were available for a cross-section comparison.",
    "unknown": "This saved result does not record consistency-pass completion.",
}
COLUMNS = ("Requirement", "Verdict", "Finding", "Sources")


def export_docx(inspection: dict[str, Any]) -> bytes:
    blocks = {block["id"]: block for block in inspection.get("blocks") or []}
    tables = [_review(review, blocks) for review in inspection["reviews"]]
    tables.append(_consistency(inspection, blocks))
    return word_document(WordReport(
        title=f"Document review: {document_name(inspection['doc_id'])}",
        context=" · ".join(display_label(inspection[key]) for key in ("indication", "intervention_class", "source_type")),
        about=(
            "PDIS Inspector read the document against each rubric below: whether each requirement "
            "is stated, and stated usably."
        ),
        notes=[
            f"{resolution['display_name']} was not run: {resolution['reason']}"
            for resolution in inspection["rubric_resolutions"]
            if resolution["status"] != "included"
        ],
        tables=tables,
    ))


def _review(review: dict[str, Any], blocks: dict[str, dict[str, Any]]) -> Table:
    units = [(section, unit) for section in review["sections"] for unit in section["units"]]
    counts = [
        (sum(unit["verdict"] == verdict for _, unit in units), label)
        for verdict, label in VERDICT_LABEL.items()
        if verdict != "section_conflict"
    ]
    # Applicability is the rubric's, so a zero there says nothing and is left out.
    counts = [(count, label) for count, label in counts if count or label != VERDICT_LABEL["not_applicable"]]
    rubric = review["rubric"]
    revision = f"Revision {rubric['revision']}. " if rubric.get("revision") else ""
    return Table(
        heading=rubric["display_name"],
        note=revision + count_summary(len(units), ("requirement", "requirements"), counts),
        columns=COLUMNS,
        widths=(3, 1.3, 5, 2.5),
        rows=[
            (
                # A unit with no variable is the section itself: a template's whole section, or a
                # guideline's requirement, whose section name is the requirement.
                f"{section['section_name']} › {unit['variable_name']}" if unit["variable_name"]
                else section["section_name"],
                VERDICT_LABEL[unit["verdict"]],
                unit["statement"],
                passage_sources(unit["cited_block_ids"], blocks, name_documents=False),
            )
            for section, unit in units
        ],
    )


def _consistency(inspection: dict[str, Any], blocks: dict[str, dict[str, Any]]) -> Table:
    findings = inspection["document_findings"]
    status = inspection["consistency_status"]
    note = CONSISTENCY_NOTE.get(status) or (
        f"{len(findings)} conflict{'' if len(findings) == 1 else 's'} between sections."
        if findings else "No conflicts between sections were found."
    )
    return Table(
        heading="Document consistency",
        note=note,
        columns=("Conflict", "Sources"),
        widths=(7, 3),
        rows=[
            (finding["statement"], passage_sources(finding["cited_block_ids"], blocks, name_documents=False))
            for finding in findings
        ],
    )
