"""A draft as a Word table, for the team to edit into their iTPP.

Every target in it is a suggestion and the document says so; every row names the sources it
rests on, so the table carries its provenance into the document it ends up in.
"""

from __future__ import annotations

from typing import Any

from shared.vocabulary import display_label
from shared.word_export import Table, WordReport, count_summary, word_document

from .contract import validate_result_contract

COLUMNS = ("Variable", "Suggested target", "Based on", "Sources")
NOT_SET = "Not set"


def export_docx(result: dict[str, Any]) -> bytes:
    validate_result_contract(result)
    variables = result["variables"]
    rows = [(variable["label"], *_row(variable)) for variable in variables]
    failed = sum(variable["status"] == "failed" for variable in variables)
    insufficient = sum(
        variable["status"] != "failed" and variable["suggestion"]["kind"] == "insufficient" for variable in variables
    )
    return word_document(WordReport(
        title="Draft iTPP targets",
        context=f"{result['display_name']} · {display_label(result['indication'])}",
        # Beside the draft it aimed, so a reader of the file sees what steered it.
        notes=[f"Intended use, as the team stated it: {result['intended_use']}"] if result["intended_use"] else [],
        about=(
            "Suggested by PDIS Drafter from comparable products' results and published guidance. "
            "Every target is a suggestion to check and edit; each row lists the sources it rests on."
        ),
        # A failure is no model's finding, so it is counted only when there is one.
        summary=count_summary(len(variables), ("variable", "variables"), (
            (len(variables) - failed - insufficient, "Suggested"),
            (insufficient, "Not enough evidence"),
            *([(failed, "Could not be suggested")] if failed else []),
        )),
        tables=[Table(columns=COLUMNS, rows=rows, widths=(2, 3, 2, 4))],
    ))


LEANS_ON_LABEL = {
    "comparable_products": "Comparable products",
    "guidance": "Published guidance",
    "both": "Comparable products and published guidance",
}


def _row(variable: dict[str, Any]) -> tuple[str, str, str]:
    if variable["status"] == "failed":
        return NOT_SET, "Could not be suggested", ""
    suggestion = variable["suggestion"]
    if suggestion["kind"] == "insufficient":
        return NOT_SET, "Not enough evidence", ""
    return _target(suggestion), LEANS_ON_LABEL[suggestion["leans_on"]], _sources(variable, suggestion["basis_ids"])


def _target(values: dict[str, Any]) -> str:
    statement = str(values.get("statement") or "").strip()
    if statement:
        return statement
    parts = [
        f"{label}: {value}"
        for label, value in (("Minimum", values.get("minimum")), ("Preferred", values.get("preferred")))
        if str(value or "").strip()
    ]
    return "\n".join(parts)


def _sources(variable: dict[str, Any], basis_ids: list[str]) -> str:
    by_id = {observation["id"]: observation for observation in variable["observations"]}
    lines = []
    for identifier in basis_ids:
        observation = by_id[identifier]
        # The year, which every stated date has: a month or day would claim more than some state.
        about = ", ".join(filter(None, (observation["source_label"], (observation["published_at"] or "")[:4])))
        lines.append(f"{observation['title']} ({about}) {observation['url']}".strip())
    return "\n".join(dict.fromkeys(lines))
