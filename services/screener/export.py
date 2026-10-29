"""A gate review as export tables, for a PPL to take back to the grantee.

The page's panels in its order - partly answered first, the one state with a specific ask
attached, then not found, then answered - each grouped by discipline with the questions the
gate requires before the anticipatory ones. Questions that do not apply to this product are
counted, not listed, as on the page.
"""

from __future__ import annotations

from typing import Any

from shared.vocabulary import display_label
from shared.report_export import ExportReport, Table, count_summary, passage_sources

COLUMNS = ("Discipline", "Question", "Requirement", "What the documents say", "Sources")

#: The page's panels and their titles, in its order.
PANELS = (
    ("partly_answered", "Partly answered",
     "Some of the question is answered and some is not. Each says what is still not stated."),
    ("not_found", "Not found in the documents",
     "Nothing in the supplied material addresses these. Each shows the discipline that owns it."),
    ("answered", "Answered", "What the supplied material already answers."),
)
#: `QUESTION_STATE_LABEL` and `QUESTION_REQUIREMENT_LABEL` in the web's `lib/api.ts`.
STATE_LABEL = {"answered": "Answered", "partly_answered": "Partly answered", "not_found": "Not found", "not_applicable": "N/A"}
REQUIREMENT_LABEL = {"required": "Required", "anticipatory": "Anticipatory"}


def export_report(review: dict[str, Any]) -> ExportReport:
    blocks = {block["id"]: block for block in review.get("blocks") or []}
    several = len(review["documents"]) > 1
    # Disciplines as the bank lists them, each question kept with its discipline.
    questions = [(discipline, question) for discipline in review["disciplines"] for question in discipline["questions"]]
    count = {state: sum(question["state"] == state for _, question in questions) for state in STATE_LABEL}
    open_required = sum(
        question["requirement"] == "required" and question["state"] in {"partly_answered", "not_found"}
        for _, question in questions
    )
    notes = [f"{open_required} question{' this gate requires is' if open_required == 1 else 's this gate requires are'} still unanswered."]
    if count["not_applicable"]:
        apart = count["not_applicable"]
        notes.append(f"{apart} question{' does' if apart == 1 else 's do'} not apply to this product and "
                     f"{'is' if apart == 1 else 'are'} not listed.")
    if review.get("bank_source"):
        notes.append(f"Questions from {review['bank_source']}")

    def rows(state: str) -> list[tuple[str, ...]]:
        in_state = [(discipline, question) for discipline, question in questions if question["state"] == state]
        # The page's order: by discipline, required before anticipatory, bank order within each.
        position = {discipline["id"]: index for index, discipline in enumerate(review["disciplines"])}
        in_state.sort(key=lambda pair: (position[pair[0]["id"]], pair[1]["requirement"] != "required"))
        return [
            (
                discipline["label"],
                f"{question['text']} ({question['id']})",
                REQUIREMENT_LABEL.get(question["requirement"], question["requirement"]),
                _answer(question),
                passage_sources(question["cited_block_ids"], blocks, name_documents=several),
            )
            for discipline, question in in_state
        ]

    return ExportReport(
        title=f"Stage gate screen: {review['gate_label']}",
        context=" · ".join((
            display_label(review["indication"]), display_label(review["intervention_class"]),
            f"{len(review['documents'])} document{'s' if len(review['documents']) != 1 else ''}",
        )),
        about=(
            "PDIS Screener read the supplied documents against this gate's question bank: what "
            "they answer, what remains open, and which discipline owns each question."
        ),
        summary=count_summary(
            len(questions) - count["not_applicable"], ("question", "questions"),
            ((count[state], STATE_LABEL[state]) for state in ("answered", "partly_answered", "not_found")),
        ),
        notes=notes,
        tables=[
            Table(heading=title, note=description, columns=COLUMNS, rows=rows(state), widths=(2, 4, 1.3, 4, 3))
            for state, title, description in PANELS
            if count[state]
        ],
    )


def _answer(question: dict[str, Any]) -> str:
    if question["state"] == "not_found":
        return ""
    if question["state"] == "partly_answered":
        return f"{question['statement']}\nStill not stated: {question['missing']}"
    return question["statement"]
