"""Expert end to end: a real DOCX in, a complete gate review out.

Every other stage is unit-tested, but nothing exercised the wiring between them —
resolve's output feeding the assessor, blocks reaching the right questions, and the
contract running on what the pipeline actually assembles. Those lines fail at
runtime rather than at build time, so this is the test that would have caught it.

The model client is a fake. What is being tested is the pipeline, not the provider.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from services.expert import (
    ContextItem,
    DocumentInput,
    GateConfig,
    QuestionSpec,
    find_config,
    run_pipeline,
)
from services.expert.models import DisciplineSpec
from services.expert.stages.assessor import (
    DECISION_NOT_FOUND,
    DECISION_FROM_CONTEXT,
    DECISION_FROM_DOCUMENT,
)


def write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))


class ScriptedClient:
    """Returns a queued decision per call, and records what it was asked.

    Also answers chunker's own model calls, which return a different shape; anything
    it does not recognise gets an empty object so the parse still completes.
    """

    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = list(decisions)
        self.triage_calls: list[str] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        if schema_name == "expert_question_triage":
            self.triage_calls.append(user_message)
            return self.decisions.pop(0) if self.decisions else {
                "decision": DECISION_NOT_FOUND,
                "statement": "Nothing supplied answers this.",
                "missing": "",
                "block_ids": [],
                "context_label": "",
            }
        if schema_name == "chunker_section_labels":
            # Chunker requires exactly one label per supplied block, drawn from its
            # taxonomy. Read both out of the schema it built, so this fake stays
            # correct if the parse contract changes.
            ids = schema["properties"]["labels"]["items"]["properties"]["id"]["enum"]
            taxonomy = schema["properties"]["labels"]["items"]["properties"][
                "section_label"
            ]["enum"]
            return {
                "labels": [
                    {"id": block_id, "section_label": taxonomy[0], "confidence": "high"}
                    for block_id in ids
                ]
            }
        return {}


def bank(*questions: QuestionSpec) -> GateConfig:
    return GateConfig(
        org="bmgf",
        gate_id="lcs",
        gate_label="Lead Chemical Series Selection",
        ordinal=1,
        intervention_classes=frozenset({"drug"}),
        mirrors="Stage Gate Questions - All Gates.docx, test fixture",
        disciplines=(
            DisciplineSpec(id="cp", label="Clinical Pharmacology", questions=questions),
        ),
    )


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.itpp = self.root / "profile.docx"
        write_docx(
            self.itpp,
            [
                "Target Product Profile",
                "Dosing regimen: one dose, annually.",
                "Procurement price: under USD 3.00 per dose.",
            ],
        )

    def run_expert(
        self,
        config: GateConfig,
        decisions: list[dict],
        *,
        context_items: list[ContextItem] | None = None,
    ):
        client = ScriptedClient(decisions)
        review = run_pipeline(
            [
                DocumentInput(
                    file_path=str(self.itpp), source_type="itpp", doc_id="profile"
                )
            ],
            org="bmgf",
            intervention_class="drug",
            indication="malaria",
            config=config,
            llm_client=client,
            context_items=context_items or [],
        )
        return review, client

    def test_every_applicable_question_reaches_the_model(self) -> None:
        """Only a question whose own text restricts a class is withheld.

        Not whether the gate requires it now: an anticipatory question is read against
        the material exactly like a required one, because the distinction is about the
        review rather than about the documents.
        """
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?"),
            QuestionSpec(id="Q2", text="Is the plan costed?", requirement="anticipatory"),
            QuestionSpec(id="Q3", text="Has the procedure been tested?"),
            QuestionSpec(
                id="Q4",
                text="For biologics: are developability metrics stated?",
                applies_to=frozenset({"monoclonal_antibody"}),
            ),
        )
        review, client = self.run_expert(config, [])
        states = {item.id: item.state for item in review.assessments()}
        self.assertEqual(states["Q1"], "not_found")
        self.assertEqual(states["Q2"], "not_found")
        self.assertEqual(states["Q3"], "not_found")
        self.assertEqual(states["Q4"], "not_applicable")
        self.assertEqual(len(review.assessments()), 4)
        self.assertEqual(len(client.triage_calls), 3)

    def test_the_requirement_survives_onto_the_result(self) -> None:
        """Carried for the same reason as the text: a saved file has no bank to look it
        up in, and it is what separates a gate blocker from early warning."""
        config = bank(
            QuestionSpec(id="Q1", text="Is the plan costed?", requirement="anticipatory")
        )
        review, _ = self.run_expert(config, [])
        assessment = review.assessments()[0]
        self.assertEqual(assessment.state, "not_found")
        self.assertEqual(assessment.requirement, "anticipatory")

    def test_the_model_is_not_told_whether_a_question_is_required(self) -> None:
        """A model told a question is only anticipatory would read the material less
        carefully for it, and the same triage has to run either way."""
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?", requirement="anticipatory")
        )
        _, client = self.run_expert(config, [])
        self.assertNotIn("anticipatory", client.triage_calls[0].lower())

    def test_every_question_sees_the_same_material(self) -> None:
        """Identical context per call is what makes the prompt prefix cacheable."""
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?"),
            QuestionSpec(id="Q2", text="Is the plan costed?"),
        )
        _, client = self.run_expert(config, [])
        self.assertEqual(len(client.triage_calls), 2)
        prefixes = {call.split("Question (")[0] for call in client.triage_calls}
        self.assertEqual(len(prefixes), 1, "the material differed between questions")

    def test_the_uploaded_document_reaches_the_prompt(self) -> None:
        config = bank(QuestionSpec(id="Q1", text="Is dosing stated?"))
        _, client = self.run_expert(config, [])
        self.assertEqual(len(client.triage_calls), 1)
        self.assertIn("Dosing regimen", client.triage_calls[0])

    def test_an_answer_carries_the_blocks_the_document_produced(self) -> None:
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?")
        )
        # Discover the real block ids by running once, then answer citing one.
        first, _ = self.run_expert(config, [])
        self.assertTrue(first.blocks, "the document produced no blocks")
        block_id = first.blocks[0].id
        self.assertTrue(block_id.startswith("profile"), block_id)

        review, _ = self.run_expert(
            config,
            [
                {
                    "decision": DECISION_FROM_DOCUMENT,
                    "statement": "The profile states one dose annually.",
                    "missing": "",
                    "block_ids": [block_id],
                    "context_label": "",
                }
            ],
        )
        answered = review.assessments()[0]
        self.assertEqual(answered.state, "answered")
        self.assertEqual(answered.source, "document")
        self.assertEqual(answered.cited_block_ids, [block_id])

    def test_context_answers_carry_a_label_and_no_lineage(self) -> None:
        config = bank(
            QuestionSpec(id="Q1", text="What is the COGS?")
        )
        review, _ = self.run_expert(
            config,
            [
                {
                    "decision": DECISION_FROM_CONTEXT,
                    "statement": "The report gives USD 1.20 per dose.",
                    "missing": "",
                    "block_ids": [],
                    "context_label": "CMC Report",
                }
            ],
            context_items=[ContextItem(label="CMC Report", text="COGS is USD 1.20")],
        )
        answered = review.assessments()[0]
        self.assertEqual(answered.source, "context")
        self.assertEqual(answered.context_label, "CMC Report")
        self.assertEqual(answered.cited_block_ids, [])
        # The label travels; the text does not.
        self.assertEqual(review.context_labels, ["CMC Report"])

    def test_the_context_text_is_never_carried_on_the_result(self) -> None:
        config = bank(
            QuestionSpec(id="Q1", text="What is the COGS?")
        )
        secret = "COGS is USD 1.20 and this string must not survive"
        review, _ = self.run_expert(
            config,
            [],
            context_items=[ContextItem(label="CMC Report", text=secret)],
        )
        self.assertNotIn(secret, repr(review))

    def test_operational_questions_are_assessed_rather_than_withheld(self) -> None:
        """No document holds these, but deciding that was a guess. Ask, and report."""
        config = bank(
            QuestionSpec(id="Q1", text="Has the procedure been tested?"),
            QuestionSpec(id="Q2", text="Would we fund this today?"),
        )
        review, client = self.run_expert(config, [])
        self.assertEqual(len(client.triage_calls), 2)
        self.assertEqual(
            [item.state for item in review.assessments()],
            ["not_found", "not_found"],
        )

    def test_a_bank_that_applies_to_nothing_fails_before_parsing(self) -> None:
        config = bank(
            QuestionSpec(
                id="Q1", text="Developability metrics?", applies_to=frozenset({"monoclonal_antibody"})
            )
        )
        with self.assertRaises(ValueError) as caught:
            self.run_expert(config, [])
        self.assertIn("drug", str(caught.exception))

    def test_a_run_without_documents_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_pipeline(
                [],
                org="bmgf",
                intervention_class="drug",
                indication="malaria",
                config=bank(QuestionSpec(id="Q1", text="t")),
                llm_client=ScriptedClient([]),
            )

    def test_two_context_items_sharing_a_label_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.run_expert(
                bank(QuestionSpec(id="Q1", text="t")),
                [],
                context_items=[
                    ContextItem(label="Report", text="one"),
                    ContextItem(label="Report", text="two"),
                ],
            )

    def test_the_shipped_bank_runs_end_to_end(self) -> None:
        """The real LCS bank, not a fixture: 80 questions, one document.

        Every question reaches the model, because no LCS question's text restricts
        itself to a class other than vaccine. That is the honest cost of not guessing.
        """
        config = find_config("bmgf", "lcs")
        review, client = self.run_expert(config, [])
        self.assertEqual(len(review.assessments()), len(config.questions()))
        self.assertEqual(
            [discipline.id for discipline in review.disciplines],
            [discipline.id for discipline in config.disciplines],
        )
        applicable = [q for _, q in config.questions() if q.applies("vaccine")]
        self.assertEqual(len(client.triage_calls), len(applicable))


if __name__ == "__main__":
    unittest.main()
